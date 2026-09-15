"""
Milestone 6.3: Autonomous SEO Monitoring Service Layer.
Continuously monitors project SEO state across rankings, page status, audit issues,
and keyword visibility; maintains persistent baselines and change detection state;
detects meaningful anomalies and recoveries; and produces SEOEvents dispatched
through the 6.2 ingestion pipeline without bypassing core architecture.
"""
import logging
import time
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.db import transaction
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    AuditIssue,
    AuditStatus,
    IssueSeverity,
    Keyword,
    KeywordRanking,
    MonitoringSnapshot,
    MonitoringState,
    MonitorStatus,
    MonitorType,
    SEOEvent,
    SEOEventSeverity,
    SEOEventStatus,
    SEOEventType,
    SiteAudit,
)
from apps.seo.services.agent_events import (
    AgentEvent,
    AgentEventPublisher,
    AgentEventType,
    InMemoryEventPublisher,
)
from apps.seo.services.event_ingestion import SEOEventIngestionService

logger = logging.getLogger(__name__)

# Default deterministic thresholds
DEFAULT_RANKING_DROP_THRESHOLD = 3
DEFAULT_AUDIT_CRITICAL_INCREASE_THRESHOLD = 2
DEFAULT_AUDIT_SCORE_DROP_THRESHOLD = 10
DEFAULT_VISIBILITY_DROP_THRESHOLD = 5.0
DEFAULT_HTTP_TIMEOUT_SECONDS = 5


class MonitoringThresholdPolicy:
    """
    Centralized, deterministic threshold policy for autonomous SEO change detection.
    Evaluates whether an observed change is significant or insignificant, or if a
    previous problem state has recovered to healthy.
    """

    @classmethod
    def evaluate_ranking_change(
        cls,
        previous_val: Dict[str, Any],
        current_val: Dict[str, Any],
        baseline_val: Dict[str, Any],
        threshold: int = DEFAULT_RANKING_DROP_THRESHOLD,
    ) -> Tuple[bool, bool, str, str]:
        """
        Evaluate ranking change.
        Returns (is_significant, is_recovery, explanation, severity).
        """
        curr_pos = current_val.get("position", 100)
        prev_pos = previous_val.get("position", curr_pos)
        base_pos = baseline_val.get("position", prev_pos)

        # Drop is positive number (e.g. rank 4 -> 12 is drop of 8)
        drop = curr_pos - prev_pos

        # Check recovery: was previous an anomaly and now returned to or beaten baseline
        is_recovery = False
        if prev_pos > base_pos and curr_pos <= base_pos:
            is_recovery = True
            explanation = f"Ranking recovered from #{prev_pos} to #{curr_pos} (baseline: #{base_pos})"
            return True, True, explanation, SEOEventSeverity.LOW

        if drop >= threshold:
            severity = SEOEventSeverity.MEDIUM
            if drop >= 8:
                severity = SEOEventSeverity.HIGH
            if drop >= 15 or curr_pos >= 50:
                severity = SEOEventSeverity.CRITICAL

            explanation = (
                f"Ranking dropped by {drop} positions (from #{prev_pos} to #{curr_pos}, baseline #{base_pos}), "
                f"exceeding threshold of {threshold}"
            )
            return True, False, explanation, severity

        explanation = f"Ranking shift of {drop} positions (from #{prev_pos} to #{curr_pos}) below threshold ({threshold})"
        return False, False, explanation, SEOEventSeverity.LOW

    @classmethod
    def evaluate_page_status(
        cls,
        previous_val: Dict[str, Any],
        current_val: Dict[str, Any],
        baseline_val: Dict[str, Any],
    ) -> Tuple[bool, bool, str, str]:
        """
        Evaluate page HTTP status transition.
        Returns (is_significant, is_recovery, explanation, severity).
        """
        curr_code = current_val.get("status_code", 200)
        curr_err = current_val.get("is_error", False) or curr_code >= 400
        prev_code = previous_val.get("status_code", 200)
        prev_err = previous_val.get("is_error", False) or prev_code >= 400

        # Check recovery: previous had error, current is healthy 200
        if prev_err and not curr_err and curr_code == 200:
            explanation = f"Page status recovered from HTTP {prev_code} to HTTP {curr_code}"
            return True, True, explanation, SEOEventSeverity.LOW

        if curr_err:
            severity = SEOEventSeverity.CRITICAL if curr_code >= 500 or curr_code == 0 else SEOEventSeverity.HIGH
            err_name = "Server error" if curr_code >= 500 else ("Client error" if curr_code >= 400 else "Connection timeout")
            explanation = f"{err_name} detected: HTTP {curr_code} on page (previously HTTP {prev_code})"
            return True, False, explanation, severity

        explanation = f"Page status HTTP {curr_code} is healthy"
        return False, False, explanation, SEOEventSeverity.LOW

    @classmethod
    def evaluate_audit_change(
        cls,
        previous_val: Dict[str, Any],
        current_val: Dict[str, Any],
        baseline_val: Dict[str, Any],
        crit_threshold: int = DEFAULT_AUDIT_CRITICAL_INCREASE_THRESHOLD,
        score_threshold: int = DEFAULT_AUDIT_SCORE_DROP_THRESHOLD,
    ) -> Tuple[bool, bool, str, str]:
        """
        Evaluate site audit findings change.
        Returns (is_significant, is_recovery, explanation, severity).
        """
        curr_crit = current_val.get("critical_issues", 0)
        prev_crit = previous_val.get("critical_issues", curr_crit)
        base_crit = baseline_val.get("critical_issues", prev_crit)

        curr_score = current_val.get("score", 100)
        prev_score = previous_val.get("score", curr_score)
        score_drop = prev_score - curr_score

        crit_increase = curr_crit - prev_crit

        # Recovery check
        if prev_crit > base_crit and curr_crit <= base_crit:
            explanation = f"Audit issues resolved: critical count recovered from {prev_crit} to {curr_crit}"
            return True, True, explanation, SEOEventSeverity.LOW

        if crit_increase >= crit_threshold or score_drop >= score_threshold:
            severity = SEOEventSeverity.CRITICAL if crit_increase >= 5 or score_drop >= 20 else SEOEventSeverity.HIGH
            explanation = (
                f"Audit degradation detected: +{crit_increase} critical issues (from {prev_crit} to {curr_crit}) "
                f"or score drop of -{score_drop} pts (score: {curr_score})"
            )
            return True, False, explanation, severity

        explanation = f"Audit fluctuation (+{crit_increase} critical, -{score_drop} score) below threshold"
        return False, False, explanation, SEOEventSeverity.LOW

    @classmethod
    def evaluate_visibility_change(
        cls,
        previous_val: Dict[str, Any],
        current_val: Dict[str, Any],
        baseline_val: Dict[str, Any],
        threshold: float = DEFAULT_VISIBILITY_DROP_THRESHOLD,
    ) -> Tuple[bool, bool, str, str]:
        """
        Evaluate aggregate keyword visibility change.
        Returns (is_significant, is_recovery, explanation, severity).
        """
        curr_vis = float(current_val.get("visibility_score", 100.0))
        prev_vis = float(previous_val.get("visibility_score", curr_vis))
        base_vis = float(baseline_val.get("visibility_score", prev_vis))

        drop = round(prev_vis - curr_vis, 1)

        # Recovery check
        if prev_vis < base_vis and curr_vis >= base_vis:
            explanation = f"Keyword visibility recovered from {prev_vis} to {curr_vis} pts (baseline: {base_vis})"
            return True, True, explanation, SEOEventSeverity.LOW

        if drop >= threshold:
            severity = SEOEventSeverity.HIGH if drop >= 10.0 else SEOEventSeverity.MEDIUM
            explanation = (
                f"Keyword visibility declined by -{drop} pts (from {prev_vis} to {curr_vis}, baseline: {base_vis}), "
                f"exceeding threshold of {threshold} pts"
            )
            return True, False, explanation, severity

        explanation = f"Keyword visibility change of {drop} pts below threshold ({threshold} pts)"
        return False, False, explanation, SEOEventSeverity.LOW


class RankingMonitor:
    """Specialized monitor for observing tracked keyword rankings."""

    @classmethod
    def observe(cls, project: Project) -> List[Dict[str, Any]]:
        observations = []
        keywords = Keyword.objects.filter(project=project, is_active=True)
        for kw in keywords:
            latest_ranking = (
                KeywordRanking.objects.filter(keyword=kw)
                .order_by("-recorded_at", "-created_at")
                .first()
            )
            if latest_ranking:
                observations.append({
                    "metric_key": f"keyword:{kw.id}",
                    "keyword_id": kw.id,
                    "keyword": kw.keyword,
                    "position": latest_ranking.position,
                    "ranking_url": latest_ranking.ranking_url or project.website_url,
                    "search_engine": latest_ranking.search_engine,
                    "observed_at": latest_ranking.created_at.isoformat() if latest_ranking.created_at else timezone.now().isoformat(),
                })
        return observations


class PageStatusMonitor:
    """Specialized monitor for observing live page HTTP statuses."""

    @classmethod
    def probe_url(cls, url: str, timeout: int = DEFAULT_HTTP_TIMEOUT_SECONDS) -> Dict[str, Any]:
        """Perform lightweight, safe HTTP probe of a target page URL."""
        start = time.time()
        try:
            # Use safe HEAD request first with fallback to GET
            resp = requests.head(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "DoxaRank-Monitor/1.0"})
            duration_ms = int((time.time() - start) * 1000)
            return {
                "status_code": resp.status_code,
                "is_error": resp.status_code >= 400,
                "latency_ms": duration_ms,
                "final_url": resp.url,
            }
        except requests.RequestException as exc:
            duration_ms = int((time.time() - start) * 1000)
            # Differentiate timeout vs socket error
            is_timeout = isinstance(exc, requests.Timeout)
            return {
                "status_code": 504 if is_timeout else 500,
                "is_error": True,
                "latency_ms": duration_ms,
                "error_details": str(exc)[:200],
            }

    @classmethod
    def observe(cls, project: Project) -> List[Dict[str, Any]]:
        observations = []
        target_url = project.website_url
        if target_url:
            probe = cls.probe_url(target_url)
            observations.append({
                "metric_key": f"url:{target_url}",
                "url": target_url,
                "status_code": probe["status_code"],
                "is_error": probe["is_error"],
                "latency_ms": probe.get("latency_ms", 0),
                "error_details": probe.get("error_details", ""),
            })
        return observations


class SEOAuditMonitor:
    """Specialized monitor for observing site audit critical issue spikes and score drops."""

    @classmethod
    def observe(cls, project: Project) -> List[Dict[str, Any]]:
        observations = []
        latest_audit = (
            SiteAudit.objects.filter(project=project, status=AuditStatus.COMPLETED)
            .order_by("-completed_at", "-created_at")
            .first()
        )
        if latest_audit:
            crit_count = latest_audit.issues.filter(severity=IssueSeverity.CRITICAL).count()
            warn_count = latest_audit.issues.filter(severity=IssueSeverity.WARNING).count()
            observations.append({
                "metric_key": "audit:site_health",
                "audit_id": latest_audit.id,
                "score": latest_audit.score if latest_audit.score is not None else 100,
                "critical_issues": crit_count,
                "warning_issues": warn_count,
                "total_issues": latest_audit.issues.count(),
                "completed_at": latest_audit.completed_at.isoformat() if latest_audit.completed_at else timezone.now().isoformat(),
            })
        return observations


class KeywordVisibilityMonitor:
    """Specialized monitor for observing aggregate keyword visibility shifts."""

    @classmethod
    def observe(cls, project: Project) -> List[Dict[str, Any]]:
        keywords = Keyword.objects.filter(project=project, is_active=True)
        total_kw = keywords.count()
        if total_kw == 0:
            return []

        top_3 = 0
        top_10 = 0
        top_20 = 0

        positions = []
        for kw in keywords:
            rank = (
                KeywordRanking.objects.filter(keyword=kw)
                .order_by("-recorded_at", "-created_at")
                .first()
            )
            if rank:
                positions.append(rank.position)
                pos = rank.position
                if pos <= 3:
                    top_3 += 1
                if pos <= 10:
                    top_10 += 1
                if pos <= 20:
                    top_20 += 1

        if not positions:
            return []

        # Smooth deterministic visibility score based on position distribution
        avg_pos = round(sum(positions) / len(positions), 1)
        vis_score = round(max(0.0, min(100.0, 100.0 - (avg_pos - 1.0) * 1.5)), 1)

        return [{
            "metric_key": "visibility:aggregate",
            "visibility_score": vis_score,
            "average_position": avg_pos,
            "total_keywords": total_kw,
            "top_3_count": top_3,
            "top_10_count": top_10,
            "top_20_count": top_20,
        }]


class AutonomousMonitoringService:
    """
    Autonomous SEO Monitoring Service for Milestone 6.3.
    Executes controlled, multi-tenant monitoring cycles, maintains persistent
    baselines, evaluates deterministic thresholds, suppresses duplicate unchanged problems,
    detects recoveries, and safely produces SEOEvents via SEOEventIngestionService.
    """

    def __init__(
        self,
        publisher: Optional[AgentEventPublisher] = None,
        ingestion_service: Optional[SEOEventIngestionService] = None,
    ):
        self.publisher = publisher or InMemoryEventPublisher()
        self.ingestion_service = ingestion_service or SEOEventIngestionService(publisher=self.publisher)

    def _emit_telemetry(self, event_type: AgentEventType, project_id: int, payload: Dict[str, Any]) -> None:
        event = AgentEvent(
            event_type=event_type,
            run_id=0,
            project_id=project_id,
            sequence_number=1,
            payload=payload,
        )
        try:
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(f"[AutonomousMonitoringService] Telemetry publish failed ({event_type}): {exc}")

    def run_monitoring_cycle(self, project_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Execute an autonomous monitoring cycle across all active projects or a specified subset.
        Enforces database row-level locking per project to ensure worker concurrency safety.
        """
        cycle_id = uuid.uuid4().hex[:8]
        start_time = time.time()
        projects_qs = Project.objects.all().order_by("id")
        if project_ids:
            projects_qs = projects_qs.filter(id__in=project_ids)

        projects = list(projects_qs)
        logger.info(f"[AutonomousMonitoringService] Starting Cycle #{cycle_id} for {len(projects)} projects.")
        self._emit_telemetry(
            AgentEventType.SEO_MONITORING_CYCLE_STARTED,
            0,
            {"cycle_id": cycle_id, "project_count": len(projects)}
        )

        results = {
            "cycle_id": cycle_id,
            "projects_evaluated": len(projects),
            "successful_projects": [],
            "failed_projects": [],
            "errors": [],
            "snapshots_created": 0,
            "changes_detected": 0,
            "changes_ignored": 0,
            "events_generated": 0,
            "recoveries_detected": 0,
            "duplicates_prevented": 0,
            "failures": 0,
        }

        for project in projects:
            try:
                # Row-level lock per project to serialize concurrent monitoring workers safely
                with transaction.atomic():
                    locked_project = Project.objects.select_for_update(skip_locked=True).filter(id=project.id).first()
                    if not locked_project:
                        logger.warning(f"[AutonomousMonitoringService] Project #{project.id} is currently locked by another worker. Skipping.")
                        continue

                    proj_res = self.run_project_monitoring(locked_project)
                    results["successful_projects"].append(project.id)
                    results["snapshots_created"] += proj_res.get("snapshots_created", 0)
                    results["changes_detected"] += proj_res.get("changes_detected", 0)
                    results["changes_ignored"] += proj_res.get("changes_ignored", 0)
                    results["events_generated"] += proj_res.get("events_generated", 0)
                    results["recoveries_detected"] += proj_res.get("recoveries_detected", 0)
                    results["duplicates_prevented"] += proj_res.get("duplicates_prevented", 0)

            except Exception as exc:
                logger.exception(f"[AutonomousMonitoringService] Project #{project.id} monitoring failed: {exc}")
                results["failures"] += 1
                results["failed_projects"].append(project.id)
                results["errors"].append({"project_id": project.id, "error": str(exc)})
                self._emit_telemetry(
                    AgentEventType.SEO_MONITORING_PROJECT_FAILED,
                    project.id,
                    {"cycle_id": cycle_id, "error": str(exc)[:200]}
                )

        duration_ms = int((time.time() - start_time) * 1000)
        results["duration_ms"] = duration_ms
        self._emit_telemetry(
            AgentEventType.SEO_MONITORING_CYCLE_COMPLETED,
            0,
            results
        )
        logger.info(f"[AutonomousMonitoringService] Completed Cycle #{cycle_id} in {duration_ms}ms: {results}")
        return results

    def monitor_project(self, project: Project) -> Dict[str, Any]:
        """
        Execute all specialized monitors for a specific project.
        Enforces tenant isolation and granular per-monitor failure isolation.
        """
        now = timezone.now()
        self._emit_telemetry(
            AgentEventType.SEO_MONITORING_PROJECT_STARTED,
            project.id,
            {"project_id": project.id, "project_name": project.name}
        )

        res = {
            "project_id": project.id,
            "snapshots_created": 0,
            "changes_detected": 0,
            "changes_ignored": 0,
            "events_generated": 0,
            "recoveries_detected": 0,
            "duplicates_prevented": 0,
        }

        # 1. Ranking Monitor
        try:
            ranking_obs = RankingMonitor.observe(project)
            for obs in ranking_obs:
                m_res = self._process_observation(
                    project=project,
                    monitor_type=MonitorType.RANKING,
                    metric_key=obs["metric_key"],
                    observation=obs,
                    now=now,
                )
                self._accumulate_results(res, m_res)
        except Exception as exc:
            logger.error(f"[AutonomousMonitoringService] Ranking monitor failed for project #{project.id}: {exc}")

        # 2. Page Status Monitor
        try:
            page_obs = PageStatusMonitor.observe(project)
            for obs in page_obs:
                m_res = self._process_observation(
                    project=project,
                    monitor_type=MonitorType.PAGE_STATUS,
                    metric_key=obs["metric_key"],
                    observation=obs,
                    now=now,
                )
                self._accumulate_results(res, m_res)
        except Exception as exc:
            logger.error(f"[AutonomousMonitoringService] Page status monitor failed for project #{project.id}: {exc}")

        # 3. SEO Audit Monitor
        try:
            audit_obs = SEOAuditMonitor.observe(project)
            for obs in audit_obs:
                m_res = self._process_observation(
                    project=project,
                    monitor_type=MonitorType.SEO_AUDIT,
                    metric_key=obs["metric_key"],
                    observation=obs,
                    now=now,
                )
                self._accumulate_results(res, m_res)
        except Exception as exc:
            logger.error(f"[AutonomousMonitoringService] SEO audit monitor failed for project #{project.id}: {exc}")

        # 4. Keyword Visibility Monitor
        try:
            vis_obs = KeywordVisibilityMonitor.observe(project)
            for obs in vis_obs:
                m_res = self._process_observation(
                    project=project,
                    monitor_type=MonitorType.KEYWORD_VISIBILITY,
                    metric_key=obs["metric_key"],
                    observation=obs,
                    now=now,
                )
                self._accumulate_results(res, m_res)
        except Exception as exc:
            logger.error(f"[AutonomousMonitoringService] Visibility monitor failed for project #{project.id}: {exc}")

        self._emit_telemetry(
            AgentEventType.SEO_MONITORING_PROJECT_COMPLETED,
            project.id,
            res
        )
        return res

    run_project_monitoring = monitor_project

    def _accumulate_results(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for k in ["snapshots_created", "changes_detected", "changes_ignored", "events_generated", "recoveries_detected", "duplicates_prevented"]:
            target[k] = target.get(k, 0) + source.get(k, 0)

    def _process_observation(
        self,
        project: Project,
        monitor_type: MonitorType,
        metric_key: str,
        observation: Dict[str, Any],
        now: Any,
    ) -> Dict[str, Any]:
        """
        Core change detection & state transition processor for a single monitored metric.
        Handles baseline establishment, threshold evaluation, duplicate suppression,
        recovery detection, and SEOEvent production.
        """
        step_res = {
            "snapshots_created": 0,
            "changes_detected": 0,
            "changes_ignored": 0,
            "events_generated": 0,
            "recoveries_detected": 0,
            "duplicates_prevented": 0,
        }

        with transaction.atomic():
            state, created = MonitoringState.objects.select_for_update().get_or_create(
                project=project,
                monitor_type=monitor_type,
                metric_key=metric_key,
                defaults={
                    "current_value": observation,
                    "previous_value": observation,
                    "baseline_value": observation,
                    "status": MonitorStatus.HEALTHY,
                    "consecutive_anomalies": 0,
                    "last_checked_at": now,
                    "last_changed_at": now,
                },
            )

            # If created on this cycle, baseline is established; initial observation is healthy
            if created:
                snapshot = MonitoringSnapshot.objects.create(
                    project=project,
                    monitor_type=monitor_type,
                    metric_key=metric_key,
                    value=observation,
                    baseline_value=observation,
                    delta={},
                    status=MonitorStatus.HEALTHY,
                    is_anomaly=False,
                    is_recovery=False,
                    created_at=now,
                )
                step_res["snapshots_created"] += 1
                self._emit_telemetry(
                    AgentEventType.SEO_MONITORING_SNAPSHOT_CREATED,
                    project.id,
                    {"metric_key": metric_key, "snapshot_id": snapshot.id}
                )
                return step_res

            # Existing state: evaluate against baseline and previous value
            prev_val = state.current_value or {}
            base_val = state.baseline_value or prev_val

            # Evaluate significance based on monitor type
            if monitor_type == MonitorType.RANKING:
                is_sig, is_rec, explanation, severity = MonitoringThresholdPolicy.evaluate_ranking_change(
                    prev_val, observation, base_val
                )
            elif monitor_type == MonitorType.PAGE_STATUS:
                is_sig, is_rec, explanation, severity = MonitoringThresholdPolicy.evaluate_page_status(
                    prev_val, observation, base_val
                )
            elif monitor_type == MonitorType.SEO_AUDIT:
                is_sig, is_rec, explanation, severity = MonitoringThresholdPolicy.evaluate_audit_change(
                    prev_val, observation, base_val
                )
            elif monitor_type == MonitorType.KEYWORD_VISIBILITY:
                is_sig, is_rec, explanation, severity = MonitoringThresholdPolicy.evaluate_visibility_change(
                    prev_val, observation, base_val
                )
            else:
                is_sig, is_rec, explanation, severity = (False, False, "Unknown monitor type", SEOEventSeverity.LOW)

            # -------------------------------------------------------------
            # CASE 1: Recovery Detected (transition from ANOMALY -> HEALTHY)
            # -------------------------------------------------------------
            if is_rec:
                state.previous_value = state.current_value
                state.current_value = observation
                state.status = MonitorStatus.RECOVERED
                state.consecutive_anomalies = 0
                state.last_checked_at = now
                state.last_changed_at = now
                state.save(update_fields=[
                    "previous_value", "current_value", "status",
                    "consecutive_anomalies", "last_checked_at", "last_changed_at", "updated_at"
                ])

                snapshot = MonitoringSnapshot.objects.create(
                    project=project,
                    monitor_type=monitor_type,
                    metric_key=metric_key,
                    value=observation,
                    baseline_value=base_val,
                    delta={"explanation": explanation, "recovered": True},
                    status=MonitorStatus.RECOVERED,
                    is_anomaly=False,
                    is_recovery=True,
                    created_at=now,
                )
                step_res["snapshots_created"] += 1
                step_res["recoveries_detected"] += 1

                self._emit_telemetry(
                    AgentEventType.SEO_MONITORING_RECOVERY_DETECTED,
                    project.id,
                    {"metric_key": metric_key, "explanation": explanation}
                )

                # Generate a recovery event through 6.2 ingestion
                rec_event_type = self._map_to_event_type(monitor_type)
                try:
                    ev = self.ingestion_service.ingest_event(
                        project=project,
                        event_type=rec_event_type,
                        source=f"autonomous_monitoring.{monitor_type}",
                        severity=SEOEventSeverity.LOW,
                        payload={
                            **observation,
                            "is_recovery": True,
                            "explanation": explanation,
                        },
                        user=project.owner,
                    )
                    if isinstance(ev, SEOEvent):
                        state.last_event = ev
                        state.last_event_at = now
                        state.save(update_fields=["last_event", "last_event_at"])
                    step_res["events_generated"] += 1
                except Exception as exc:
                    logger.warning(f"[AutonomousMonitoringService] Failed to ingest recovery event: {exc}")

                return step_res

            # -------------------------------------------------------------
            # CASE 2: Deduplication / Repeated Unchanged Problem Protection
            # If the metric is already in ANOMALY status and current_value is unchanged
            # from what was already reported in previous cycle, DO NOT spam duplicate events!
            # -------------------------------------------------------------
            def _extract_core_val(val_dict: Dict[str, Any]) -> Dict[str, Any]:
                return {k: v for k, v in (val_dict or {}).items() if k not in ["observed_at", "latency_ms"]}

            is_repeated_unchanged = (
                state.status == MonitorStatus.ANOMALY
                and _extract_core_val(state.current_value) == _extract_core_val(observation)
                and state.consecutive_anomalies > 0
            )

            if is_repeated_unchanged:
                state.consecutive_anomalies += 1
                state.last_checked_at = now
                state.save(update_fields=["consecutive_anomalies", "last_checked_at", "updated_at"])

                step_res["duplicates_prevented"] += 1
                self._emit_telemetry(
                    AgentEventType.SEO_MONITORING_DUPLICATE_PREVENTED,
                    project.id,
                    {
                        "metric_key": metric_key,
                        "consecutive_anomalies": state.consecutive_anomalies,
                        "explanation": "Repeated unchanged anomaly suppressed",
                    }
                )
                return step_res

            # -------------------------------------------------------------
            # CASE 3: Insignificant Change (below threshold)
            # -------------------------------------------------------------
            if not is_sig:
                state.last_checked_at = now
                # If values differ slightly, update previous and current without triggering event
                if observation != state.current_value:
                    state.previous_value = state.current_value
                    state.current_value = observation
                    state.last_changed_at = now
                    state.save(update_fields=["previous_value", "current_value", "last_checked_at", "last_changed_at", "updated_at"])
                else:
                    state.save(update_fields=["last_checked_at", "updated_at"])

                snapshot = MonitoringSnapshot.objects.create(
                    project=project,
                    monitor_type=monitor_type,
                    metric_key=metric_key,
                    value=observation,
                    baseline_value=base_val,
                    delta={"explanation": explanation, "significant": False},
                    status=state.status,
                    is_anomaly=False,
                    is_recovery=False,
                    created_at=now,
                )
                step_res["snapshots_created"] += 1
                step_res["changes_ignored"] += 1

                self._emit_telemetry(
                    AgentEventType.SEO_MONITORING_CHANGE_IGNORED,
                    project.id,
                    {"metric_key": metric_key, "explanation": explanation}
                )
                return step_res

            # -------------------------------------------------------------
            # CASE 4: Significant Change Detected (New or Worsened Anomaly)
            # -------------------------------------------------------------
            state.previous_value = state.current_value
            state.current_value = observation
            state.status = MonitorStatus.ANOMALY
            state.consecutive_anomalies += 1
            state.last_checked_at = now
            state.last_changed_at = now
            state.last_event_at = now
            state.save(update_fields=[
                "previous_value", "current_value", "status",
                "consecutive_anomalies", "last_checked_at", "last_changed_at",
                "last_event_at", "updated_at"
            ])

            snapshot = MonitoringSnapshot.objects.create(
                project=project,
                monitor_type=monitor_type,
                metric_key=metric_key,
                value=observation,
                baseline_value=base_val,
                delta={"explanation": explanation, "severity": severity},
                status=MonitorStatus.ANOMALY,
                is_anomaly=True,
                is_recovery=False,
                created_at=now,
            )
            step_res["snapshots_created"] += 1
            step_res["changes_detected"] += 1

            self._emit_telemetry(
                AgentEventType.SEO_MONITORING_CHANGE_DETECTED,
                project.id,
                {"metric_key": metric_key, "explanation": explanation, "severity": severity}
            )

            # Produce SEOEvent and pass through 6.2 ingestion pipeline
            event_type = self._map_to_event_type(monitor_type)
            payload = self._build_event_payload(monitor_type, observation, prev_val, base_val, explanation)

            try:
                event_obj = self.ingestion_service.ingest_event(
                    project=project,
                    event_type=event_type,
                    source=f"autonomous_monitoring.{monitor_type}",
                    severity=severity,
                    payload=payload,
                    user=project.owner,
                )
                if isinstance(event_obj, SEOEvent):
                    state.last_event = event_obj
                    state.save(update_fields=["last_event"])
                step_res["events_generated"] += 1

                self._emit_telemetry(
                    AgentEventType.SEO_MONITORING_EVENT_CREATED,
                    project.id,
                    {"metric_key": metric_key, "event_id": getattr(event_obj, "id", None), "event_type": event_type}
                )
            except Exception as exc:
                logger.error(f"[AutonomousMonitoringService] Error ingesting SEOEvent for {metric_key}: {exc}")

        return step_res

    def _map_to_event_type(self, monitor_type: MonitorType) -> SEOEventType:
        if monitor_type == MonitorType.RANKING:
            return SEOEventType.RANKING_CHANGE
        elif monitor_type == MonitorType.PAGE_STATUS:
            return SEOEventType.PAGE_STATUS_CHANGE
        elif monitor_type == MonitorType.SEO_AUDIT:
            return SEOEventType.SEO_AUDIT_CHANGE
        elif monitor_type == MonitorType.KEYWORD_VISIBILITY:
            return SEOEventType.KEYWORD_VISIBILITY_CHANGE
        return SEOEventType.RANKING_CHANGE

    def _build_event_payload(
        self,
        monitor_type: MonitorType,
        observation: Dict[str, Any],
        prev_val: Dict[str, Any],
        base_val: Dict[str, Any],
        explanation: str,
    ) -> Dict[str, Any]:
        payload = {
            **observation,
            "previous_observation": prev_val,
            "baseline_observation": base_val,
            "monitoring_explanation": explanation,
            "detected_by": "autonomous_monitoring",
        }

        if monitor_type == MonitorType.RANKING:
            curr_pos = observation.get("position", 100)
            prev_pos = prev_val.get("position", curr_pos)
            payload["rank_drop"] = max(0, curr_pos - prev_pos)
            payload["previous_rank"] = prev_pos
            payload["current_rank"] = curr_pos
            payload["new_rank"] = curr_pos
        elif monitor_type == MonitorType.PAGE_STATUS:
            payload["status_code"] = observation.get("status_code", 500)
            payload["is_error"] = observation.get("is_error", True)
            payload["url"] = observation.get("url", "")
        elif monitor_type == MonitorType.SEO_AUDIT:
            curr_crit = observation.get("critical_issues", 0)
            prev_crit = prev_val.get("critical_issues", curr_crit)
            payload["critical_issues_count"] = curr_crit
            curr_score = observation.get("score", 100)
            prev_score = prev_val.get("score", curr_score)
            payload["score_drop"] = max(0, prev_score - curr_score)
        elif monitor_type == MonitorType.KEYWORD_VISIBILITY:
            curr_vis = float(observation.get("visibility_score", 100.0))
            prev_vis = float(prev_val.get("visibility_score", curr_vis))
            payload["visibility_drop_points"] = max(0.0, round(prev_vis - curr_vis, 1))

        return payload
