"""
DoxaRank Autonomous SEO Action Planner.

Converts multi-source SEO evidence (AuditIssues, GSC metrics, SEO insights,
investigation findings) into structured, explainable, prioritized SEOActionPlans
and SEOAction proposals with deterministic risk classification, deduplication,
and verification plans.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from django.db import transaction
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    SEOActionPlan, SEOAction, ActionType, ActionStatus, ActionPriority,
    ActionPlanStatus, ActionRiskLevel, VerificationStatus,
    AuditIssue, SiteAudit, SearchAnalyticsData, SEOInsight,
    Keyword, KeywordRanking, AgentRun
)
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)
from apps.seo.services.seo_intelligence import normalize_url_path_for_matching

logger = logging.getLogger(__name__)

# Controlled vocabulary for plannable vs executable actions
EXECUTABLE_ACTION_TYPES = {
    ActionType.OPTIMIZE_TITLE,
    ActionType.UPDATE_TITLE,
    ActionType.OPTIMIZE_META_DESCRIPTION,
    ActionType.UPDATE_META_DESCRIPTION,
    ActionType.FIX_MISSING_H1,
    ActionType.FIX_CANONICAL,
    ActionType.FIX_IMAGE_ALT,
    ActionType.ADD_STRUCTURED_DATA,
    ActionType.PUBLISH_NEW_CONTENT,
}

PLANNABLE_ONLY_ACTION_TYPES = {
    ActionType.FIX_BROKEN_INTERNAL_LINK,
    ActionType.FIX_BROKEN_LINK,
    ActionType.REMOVE_REDIRECT_CHAIN,
    ActionType.IMPROVE_INTERNAL_LINKING,
    ActionType.ADD_INTERNAL_LINKS,
    ActionType.TECHNICAL_SEO_FIX,
    ActionType.INVESTIGATE_RANKING_DROP,
    ActionType.INVESTIGATE_PERFORMANCE,
    ActionType.CONTENT_REFRESH,
    ActionType.IMPROVE_CONTENT,
    ActionType.MONITOR,
    ActionType.NO_ACTION,
}

# Active statuses for deduplication
ACTIVE_ACTION_STATUSES = {
    ActionStatus.PROPOSED,
    ActionStatus.PENDING_APPROVAL,
    ActionStatus.REVIEWED,
    ActionStatus.APPROVED,
    ActionStatus.READY_TO_EXECUTE,
    ActionStatus.EXECUTING,
}

# Deterministic risk classification mapping
ACTION_RISK_MAP = {
    ActionType.OPTIMIZE_META_DESCRIPTION: ActionRiskLevel.LOW,
    ActionType.UPDATE_META_DESCRIPTION: ActionRiskLevel.LOW,
    ActionType.FIX_IMAGE_ALT: ActionRiskLevel.LOW,
    ActionType.ADD_STRUCTURED_DATA: ActionRiskLevel.LOW,
    ActionType.CONTENT_REFRESH: ActionRiskLevel.LOW,
    ActionType.MONITOR: ActionRiskLevel.LOW,
    ActionType.NO_ACTION: ActionRiskLevel.LOW,

    ActionType.OPTIMIZE_TITLE: ActionRiskLevel.MEDIUM,
    ActionType.UPDATE_TITLE: ActionRiskLevel.MEDIUM,
    ActionType.FIX_MISSING_H1: ActionRiskLevel.MEDIUM,
    ActionType.FIX_BROKEN_INTERNAL_LINK: ActionRiskLevel.MEDIUM,
    ActionType.FIX_BROKEN_LINK: ActionRiskLevel.MEDIUM,
    ActionType.IMPROVE_INTERNAL_LINKING: ActionRiskLevel.MEDIUM,
    ActionType.ADD_INTERNAL_LINKS: ActionRiskLevel.MEDIUM,
    ActionType.IMPROVE_CONTENT: ActionRiskLevel.MEDIUM,
    ActionType.OPTIMIZE_EXISTING_CONTENT: ActionRiskLevel.MEDIUM,
    ActionType.PUBLISH_NEW_CONTENT: ActionRiskLevel.MEDIUM,
    ActionType.INVESTIGATE_RANKING_DROP: ActionRiskLevel.LOW,
    ActionType.INVESTIGATE_PERFORMANCE: ActionRiskLevel.LOW,

    ActionType.FIX_CANONICAL: ActionRiskLevel.HIGH,
    ActionType.REMOVE_REDIRECT_CHAIN: ActionRiskLevel.CRITICAL,
    ActionType.UPDATE_SLUG: ActionRiskLevel.HIGH,
    ActionType.TECHNICAL_SEO_FIX: ActionRiskLevel.HIGH,
}

RISK_SEVERITY_ORDER = {
    ActionRiskLevel.LOW: 1,
    ActionRiskLevel.MEDIUM: 2,
    ActionRiskLevel.HIGH: 3,
    ActionRiskLevel.CRITICAL: 4,
}


class SEOActionPlanner:
    """
    Autonomous SEO Action Planning Engine.
    Synthesizes multi-source empirical evidence into structured action proposals,
    classifies operational risk deterministically, enforces deduplication,
    and structures verification strategies.
    """

    def __init__(
        self,
        project: Project,
        publisher: Optional[AgentEventPublisher] = None
    ):
        self.project = project
        self.publisher = publisher or get_event_publisher()

    def _emit_event(
        self,
        event_type: Union[AgentEventType, str],
        payload: Dict[str, Any],
        run_id: Optional[int] = None
    ) -> None:
        try:
            event = AgentEvent(
                event_type=event_type,
                run_id=run_id or 0,
                project_id=self.project.id,
                payload=payload
            )
            self.publisher.publish(event)
        except Exception as exc:
            logger.debug(f"[SEOActionPlanner] Event emission failed: {exc}")

    @staticmethod
    def classify_risk(action_type: str, details: Optional[Dict[str, Any]] = None) -> str:
        """
        Deterministic Risk Classification.
        Independent of SEO severity.
        """
        normalized_type = str(action_type).lower()
        base_risk = ACTION_RISK_MAP.get(normalized_type, ActionRiskLevel.MEDIUM)

        details = details or {}
        # Escalation rule: sitewide or multi-URL modifications escalate to CRITICAL
        if details.get("is_sitewide") or details.get("affected_urls_count", 1) > 20:
            return ActionRiskLevel.CRITICAL
        # Escalation rule: canonical rewrite on homepage or root domain
        if normalized_type == ActionType.FIX_CANONICAL and details.get("is_root_url"):
            return ActionRiskLevel.CRITICAL

        return base_risk

    @staticmethod
    def is_executable(action_type: str) -> bool:
        """Check whether an automated connector exists for this action type."""
        normalized = str(action_type).lower()
        return normalized in EXECUTABLE_ACTION_TYPES

    def build_verification_plan(
        self,
        action_type: str,
        target_url: str,
        proposed_change: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Construct a deterministic verification plan describing what crawler/fetcher
        checks to execute after applying the action.
        """
        act_type = str(action_type).lower()
        target = target_url or self.project.website_url

        if "title" in act_type:
            expected = proposed_change.get("title") or proposed_change.get("meta_title") or ""
            return {
                "method": "crawl_inspect_title",
                "target_url": target,
                "expected_property": "title",
                "expected_value": expected,
                "criteria": f"Verify <title> tag on {target} matches expected value."
            }
        elif "meta_description" in act_type:
            expected = proposed_change.get("meta_description") or proposed_change.get("description") or ""
            return {
                "method": "crawl_inspect_meta_description",
                "target_url": target,
                "expected_property": "meta_description",
                "expected_value": expected,
                "criteria": f"Verify <meta name='description'> tag on {target} is updated."
            }
        elif "h1" in act_type:
            expected = proposed_change.get("h1") or ""
            return {
                "method": "crawl_inspect_h1",
                "target_url": target,
                "expected_property": "h1",
                "expected_value": expected,
                "criteria": f"Verify primary <h1> heading is present and non-empty on {target}."
            }
        elif "canonical" in act_type:
            expected = proposed_change.get("canonical_url") or target
            return {
                "method": "crawl_inspect_canonical",
                "target_url": target,
                "expected_property": "canonical_url",
                "expected_value": expected,
                "criteria": f"Verify <link rel='canonical'> on {target} points to {expected}."
            }
        elif "image_alt" in act_type:
            return {
                "method": "crawl_inspect_image_alts",
                "target_url": target,
                "expected_property": "image_alt_tags",
                "criteria": f"Verify all images on {target} have non-empty alt text attributes."
            }
        elif "broken" in act_type or "link" in act_type:
            return {
                "method": "http_status_check",
                "target_url": target,
                "expected_status_code": 200,
                "criteria": f"Verify target URL {target} returns HTTP 200 OK without 4xx/5xx errors."
            }
        elif "redirect" in act_type:
            return {
                "method": "http_redirect_chain_check",
                "target_url": target,
                "max_redirects": 1,
                "criteria": f"Verify URL {target} does not trigger a redirect chain (>1 hop)."
            }
        elif "structured_data" in act_type:
            return {
                "method": "crawl_inspect_json_ld",
                "target_url": target,
                "expected_property": "schema_json_ld",
                "criteria": f"Verify valid JSON-LD structured data block is present on {target}."
            }
        else:
            return {
                "method": "live_site_crawl",
                "target_url": target,
                "criteria": f"Perform post-execution crawl to confirm target URL health."
            }

    def is_duplicate_action(self, action_type: str, target_url: str) -> bool:
        """
        Deterministic deduplication check.
        Returns True if an active SEOAction already exists with same action_type and target_url.
        """
        norm_type = str(action_type).lower()
        norm_target = normalize_url_path_for_matching(target_url or '')

        # Check existing actions in active statuses
        existing_actions = SEOAction.objects.filter(
            project=self.project,
            status__in=ACTIVE_ACTION_STATUSES,
            action_type=norm_type
        ).only('id', 'target_url')

        for act in existing_actions:
            if normalize_url_path_for_matching(act.target_url) == norm_target:
                return True

        return False

    def plan_from_audit_issues(
        self,
        audit: Optional[SiteAudit] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Generate action proposals directly from deterministic SiteAudit issues.
        """
        proposals: List[Dict[str, Any]] = []

        query = AuditIssue.objects.filter(audit__project=self.project)
        if audit:
            query = query.filter(audit=audit)
        else:
            latest_audit = SiteAudit.objects.filter(project=self.project, status='completed').order_by('-created_at').first()
            if latest_audit:
                query = query.filter(audit=latest_audit)

        issues = query.order_by('-created_at')[:limit * 3]

        for issue in issues:
            itype = issue.issue_type.lower()
            target_url = issue.page_url or self.project.website_url
            mapped_type: Optional[str] = None
            proposed_changes: Dict[str, Any] = {}
            title = f"Fix {issue.title or issue.issue_type} on {target_url}"
            description = issue.description or f"Address SEO audit issue: {issue.title or issue.issue_type}."
            expected_impact = "medium" if issue.severity == "critical" else "low"
            confidence = 0.90 if issue.severity == "critical" else 0.80

            if "missing_title" in itype or "empty_title" in itype:
                mapped_type = ActionType.OPTIMIZE_TITLE
                suggested_title = f"{self.project.name} | Official Website"
                proposed_changes = {"title": suggested_title}
                title = f"Add Missing Page Title on {target_url}"
                description = "Page is currently missing a title tag. Adding a descriptive title will establish search index relevance."
                expected_impact = "high"
                confidence = 0.95
            elif "duplicate_title" in itype or "title" in itype:
                mapped_type = ActionType.OPTIMIZE_TITLE
                proposed_changes = {"title": f"{self.project.name} - Distinct Optimized Title"}
                title = f"Optimize Title Tag on {target_url}"
            elif "missing_meta_description" in itype or "meta_description" in itype:
                mapped_type = ActionType.OPTIMIZE_META_DESCRIPTION
                suggested_desc = f"Discover {self.project.name} - high-quality services, insightful articles, and trusted updates."
                proposed_changes = {"meta_description": suggested_desc}
                title = f"Add Meta Description to {target_url}"
                description = "Page is missing a meta description. Adding an engaging description improves SERP snippet quality."
                confidence = 0.90
            elif "missing_h1" in itype or "multiple_h1" in itype:
                mapped_type = ActionType.FIX_MISSING_H1
                proposed_changes = {"h1": f"{self.project.name} Overview"}
                title = f"Fix Heading 1 (H1) on {target_url}"
                description = "Ensure a single, semantic H1 tag is present at the top of the page."
                confidence = 0.88
            elif "canonical" in itype:
                mapped_type = ActionType.FIX_CANONICAL
                proposed_changes = {"canonical_url": target_url}
                title = f"Correct Canonical Tag on {target_url}"
                description = "Self-referencing canonical tag needed to prevent duplicate content indexing."
                confidence = 0.85
            elif "image_alt" in itype or "missing_alt" in itype:
                mapped_type = ActionType.FIX_IMAGE_ALT
                proposed_changes = {"images": [{"url": target_url, "suggested_alt": f"{self.project.name} visual asset"}]}
                title = f"Add Image Alt Attributes on {target_url}"
                description = "Images missing alt text harm accessibility and image search discovery."
                confidence = 0.85
            elif "broken" in itype or "404" in itype or "broken_internal_link" in itype:
                mapped_type = ActionType.FIX_BROKEN_INTERNAL_LINK
                proposed_changes = {"broken_url": target_url, "target_fix": "update_or_remove"}
                title = f"Fix Broken Internal Link: {target_url}"
                description = "Internal link returns 4xx/5xx status code. Update anchor href or configure redirect."
                expected_impact = "high"
                confidence = 0.95
            elif "redirect" in itype:
                mapped_type = ActionType.REMOVE_REDIRECT_CHAIN
                proposed_changes = {"source_url": target_url, "target_url": self.project.website_url}
                title = f"Remove Redirect Chain on {target_url}"
                description = "Multiple redirect hops waste crawl budget and slow page rendering."
                confidence = 0.85
            elif "structured_data" in itype:
                mapped_type = ActionType.ADD_STRUCTURED_DATA
                proposed_changes = {"schema_type": "WebPage", "url": target_url}
                title = f"Add Schema Markup to {target_url}"
                confidence = 0.80
            else:
                mapped_type = ActionType.TECHNICAL_SEO_FIX
                proposed_changes = {"issue_type": issue.issue_type, "target_url": target_url}
                title = f"Resolve Technical Issue: {issue.get_issue_type_display()} on {target_url}"
                confidence = 0.75

            # Deduplication
            if self.is_duplicate_action(mapped_type, target_url):
                logger.debug(f"[SEOActionPlanner] Skipping duplicate proposal: {mapped_type} on {target_url}")
                continue

            risk = self.classify_risk(mapped_type, {"target_url": target_url})
            verification_plan = self.build_verification_plan(mapped_type, target_url, proposed_changes)
            executable = self.is_executable(mapped_type)

            proposal = {
                "action_type": mapped_type,
                "title": title,
                "description": description,
                "reason": f"Detected during SiteAudit: {issue.title or issue.issue_type} (Severity: {issue.severity.upper()}).",
                "evidence": {
                    "source": "site_audit",
                    "audit_issue_id": issue.id,
                    "issue_type": issue.issue_type,
                    "severity": issue.severity,
                    "page_url": target_url,
                    "details": getattr(issue, 'details', {}) or {}
                },
                "target_url": target_url,
                "target_keyword": "",
                "current_state": {
                    "issue_type": issue.issue_type,
                    "severity": issue.severity,
                    "url": target_url
                },
                "proposed_change": proposed_changes,
                "expected_impact": expected_impact,
                "confidence": confidence,
                "risk_level": risk,
                "requires_approval": True,
                "verification_plan": verification_plan,
                "execution_available": executable,
            }
            proposals.append(proposal)

            if len(proposals) >= limit:
                break

        return proposals

    def plan_from_gsc_metrics(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Generate action proposals from Google Search Console analytics data
        (e.g., High Impression / Low CTR pages, page 2 keywords).
        """
        proposals: List[Dict[str, Any]] = []

        gsc_records = SearchAnalyticsData.objects.filter(
            connection__project=self.project,
            impressions__gte=50
        ).order_by('-impressions')[:limit * 3]

        for gsc in gsc_records:
            ctr = float(gsc.ctr or 0.0)
            pos = float(gsc.position or 0.0)
            imps = int(gsc.impressions or 0)
            page_url = gsc.page or self.project.website_url
            query = gsc.query or ""

            # Opportunity Pattern 1: High Impressions, Low CTR on Page 1 (CTR < 2.5%, Position <= 10)
            if imps >= 100 and ctr < 0.025 and 1.0 <= pos <= 10.0:
                action_type = ActionType.OPTIMIZE_TITLE
                if self.is_duplicate_action(action_type, page_url):
                    continue

                suggested_title = f"{query.title()} | {self.project.name}" if query else f"Optimized Guide: {self.project.name}"
                proposed_changes = {
                    "title": suggested_title,
                    "meta_description": f"Comprehensive guide to {query or 'our services'}. Read expert insights and practical steps from {self.project.name}."
                }
                verification_plan = self.build_verification_plan(action_type, page_url, proposed_changes)

                proposal = {
                    "action_type": action_type,
                    "title": f"Optimize Title & CTR for '{query or page_url}'",
                    "description": f"Page ranks at position #{pos:.1f} with {imps:,} impressions but only {ctr*100:.1f}% CTR. Rewriting the title and meta snippet will capture lost clicks.",
                    "reason": f"GSC Performance Opportunity: High impression volume ({imps:,}) with below-average CTR ({ctr*100:.1f}%) on Page 1.",
                    "evidence": {
                        "source": "google_search_console",
                        "impressions": imps,
                        "clicks": gsc.clicks,
                        "ctr": ctr,
                        "position": pos,
                        "query": query,
                        "page": page_url
                    },
                    "target_url": page_url,
                    "target_keyword": query,
                    "current_state": {
                        "impressions": imps,
                        "clicks": gsc.clicks,
                        "ctr": ctr,
                        "position": pos
                    },
                    "proposed_change": proposed_changes,
                    "expected_impact": "high",
                    "confidence": 0.88,
                    "risk_level": ActionRiskLevel.MEDIUM,
                    "requires_approval": True,
                    "verification_plan": verification_plan,
                    "execution_available": self.is_executable(action_type),
                }
                proposals.append(proposal)

            # Opportunity Pattern 2: Page 2 Striking Distance (Position 11-20)
            elif 10.5 <= pos <= 20.0 and imps >= 50:
                action_type = ActionType.IMPROVE_INTERNAL_LINKING
                if self.is_duplicate_action(action_type, page_url):
                    continue

                proposed_changes = {
                    "target_url": page_url,
                    "target_keyword": query,
                    "action": "add_contextual_internal_links"
                }
                verification_plan = self.build_verification_plan(action_type, page_url, proposed_changes)

                proposal = {
                    "action_type": action_type,
                    "title": f"Boost Striking Distance Keyword: '{query}' (Pos: #{pos:.1f})",
                    "description": f"Target page ranks on Page 2 (Pos #{pos:.1f}). Adding contextual internal links with exact-match anchor text will push it to Page 1.",
                    "reason": f"Striking distance opportunity: Query '{query}' has {imps:,} impressions and ranks on Page 2.",
                    "evidence": {
                        "source": "google_search_console",
                        "impressions": imps,
                        "clicks": gsc.clicks,
                        "ctr": ctr,
                        "position": pos,
                        "query": query,
                        "page": page_url
                    },
                    "target_url": page_url,
                    "target_keyword": query,
                    "current_state": {
                        "position": pos,
                        "impressions": imps,
                        "query": query
                    },
                    "proposed_change": proposed_changes,
                    "expected_impact": "high",
                    "confidence": 0.82,
                    "risk_level": ActionRiskLevel.MEDIUM,
                    "requires_approval": True,
                    "verification_plan": verification_plan,
                    "execution_available": self.is_executable(action_type),
                }
                proposals.append(proposal)

            if len(proposals) >= limit:
                break

        return proposals

    def plan_from_investigations(
        self,
        investigation_results: Optional[List[Any]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Generate action proposals from SEOInvestigationResult objects or stored insights.
        """
        proposals: List[Dict[str, Any]] = []
        if not investigation_results:
            return proposals

        for inv in investigation_results:
            data = inv.to_dict() if hasattr(inv, 'to_dict') else inv if isinstance(inv, dict) else {}
            if not data:
                continue

            rec = data.get('recommended_action') or {}
            raw_act_type = str(rec.get('action_type') or 'OPTIMIZE_EXISTING_CONTENT').lower()

            if raw_act_type in ['monitor', 'no_action']:
                continue

            target_url = rec.get('target_url') or data.get('target_url') or self.project.website_url
            target_query = rec.get('target_query') or data.get('target_query') or ''

            if self.is_duplicate_action(raw_act_type, target_url):
                continue

            proposed_change = rec.get('proposed_changes') or {}
            if not proposed_change:
                if 'title' in raw_act_type:
                    proposed_change = {"title": rec.get('suggested_title') or f"{self.project.name} Optimized"}
                elif 'meta_description' in raw_act_type:
                    proposed_change = {"meta_description": rec.get('suggested_description') or f"Explore {self.project.name}."}
                elif 'canonical' in raw_act_type:
                    proposed_change = {"canonical_url": target_url}
                elif 'h1' in raw_act_type:
                    proposed_change = {"h1": f"{self.project.name} Overview"}
                else:
                    proposed_change = {"target_url": target_url, "action": raw_act_type}

            risk = self.classify_risk(raw_act_type, {"target_url": target_url})
            verification_plan = self.build_verification_plan(raw_act_type, target_url, proposed_change)

            proposal = {
                "action_type": raw_act_type,
                "title": rec.get('title') or f"Apply {raw_act_type.replace('_', ' ').title()} on {target_url}",
                "description": rec.get('description') or data.get('root_cause_reason') or "SEO Investigation recommendation.",
                "reason": data.get('root_cause_reason') or f"Derived from investigation #{data.get('investigation_id', '')}.",
                "evidence": {
                    "source": "investigation",
                    "investigation_id": data.get('investigation_id', ''),
                    "opportunity_type": data.get('opportunity_type', ''),
                    "root_cause_category": data.get('root_cause_category', ''),
                    "observed_facts": data.get('observed_facts', []),
                    "inferences": data.get('inferences', []),
                    "supporting_gsc_metrics": data.get('supporting_gsc_metrics', {}),
                    "supporting_audit_issues": data.get('supporting_audit_issues', [])
                },
                "target_url": target_url,
                "target_keyword": target_query,
                "current_state": {
                    "target_url": target_url,
                    "target_query": target_query
                },
                "proposed_change": proposed_change,
                "expected_impact": str(data.get('impact_estimate') or 'medium').lower(),
                "confidence": float(data.get('confidence_score') or 0.85),
                "risk_level": risk,
                "requires_approval": True,
                "verification_plan": verification_plan,
                "execution_available": self.is_executable(raw_act_type),
            }
            proposals.append(proposal)

            if len(proposals) >= limit:
                break

        return proposals

    def create_action_plan(
        self,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        audit_id: Optional[int] = None,
        investigations: Optional[List[Any]] = None,
        user: Optional[Any] = None,
        agent_run: Optional[AgentRun] = None,
        max_actions: int = 10,
        run_id: Optional[int] = None
    ) -> SEOActionPlan:
        """
        Synthesize evidence across SiteAudits, GSC metrics, and Investigations,
        construct action proposals, persist an SEOActionPlan and child SEOAction records
        in an atomic transaction, and emit structured lifecycle events.
        """
        # 1. Collect evidence proposals
        all_proposals: List[Dict[str, Any]] = []

        # From audit
        audit = SiteAudit.objects.filter(id=audit_id, project=self.project).first() if audit_id else None
        audit_proposals = self.plan_from_audit_issues(audit=audit, limit=max_actions)
        all_proposals.extend(audit_proposals)

        # From GSC
        if len(all_proposals) < max_actions:
            gsc_proposals = self.plan_from_gsc_metrics(limit=max_actions - len(all_proposals))
            all_proposals.extend(gsc_proposals)

        # From investigations
        if investigations and len(all_proposals) < max_actions:
            inv_proposals = self.plan_from_investigations(investigations, limit=max_actions - len(all_proposals))
            all_proposals.extend(inv_proposals)

        # Fallback if no proposals were generated: provide default optimization proposal
        if not all_proposals:
            default_type = ActionType.OPTIMIZE_TITLE
            target = self.project.website_url
            proposed_change = {"title": f"{self.project.name} | Official Website"}
            v_plan = self.build_verification_plan(default_type, target, proposed_change)
            all_proposals.append({
                "action_type": default_type,
                "title": f"Establish Core Title Metadata for {self.project.name}",
                "description": f"Standardize homepage title and meta snippet to establish search engine indexing relevance.",
                "reason": "Baseline SEO optimization for project website.",
                "evidence": {"source": "baseline_rule", "website_url": target},
                "target_url": target,
                "target_keyword": "",
                "current_state": {"url": target},
                "proposed_change": proposed_change,
                "expected_impact": "medium",
                "confidence": 0.80,
                "risk_level": ActionRiskLevel.LOW,
                "requires_approval": True,
                "verification_plan": v_plan,
                "execution_available": True,
            })

        # Calculate aggregate metrics
        max_risk_level = ActionRiskLevel.LOW
        max_risk_val = 1
        for p in all_proposals:
            p_risk = p.get('risk_level', ActionRiskLevel.LOW)
            val = RISK_SEVERITY_ORDER.get(p_risk, 1)
            if val > max_risk_val:
                max_risk_val = val
                max_risk_level = p_risk

        avg_confidence = round(sum(p.get('confidence', 0.8) for p in all_proposals) / max(1, len(all_proposals)), 2)

        plan_title = title or f"SEO Action Plan: {len(all_proposals)} Optimizations ({self.project.name})"
        plan_summary = summary or (
            f"Autonomous SEO action plan generated from {len(all_proposals)} evidence-backed opportunities. "
            f"Overall risk: {max_risk_level.upper()}, Confidence: {int(avg_confidence * 100)}%."
        )

        source_evidence = {
            "total_proposals": len(all_proposals),
            "evidence_sources": list(set(p.get('evidence', {}).get('source', 'unknown') for p in all_proposals)),
            "generated_at": timezone.now().isoformat(),
            "proposals_summary": [
                {
                    "action_type": p['action_type'],
                    "target_url": p['target_url'],
                    "risk_level": p['risk_level'],
                    "execution_available": p['execution_available']
                }
                for p in all_proposals
            ]
        }

        # 2. Persist ActionPlan and Actions atomically
        with transaction.atomic():
            action_plan = SEOActionPlan.objects.create(
                project=self.project,
                created_by=user if user and getattr(user, 'is_authenticated', False) else None,
                agent_run=agent_run,
                title=plan_title,
                summary=plan_summary,
                source_evidence=source_evidence,
                status=ActionPlanStatus.PROPOSED,
                risk_level=max_risk_level,
                confidence_score=avg_confidence,
                requires_human_approval=True,
                verification_status=VerificationStatus.PENDING,
                verification_results={}
            )

            created_actions: List[SEOAction] = []
            for p in all_proposals:
                instructions = (
                    f"### Action: {p['title']}\n\n"
                    f"**Target URL:** {p['target_url']}\n"
                    f"**Action Type:** {p['action_type']}\n"
                    f"**Risk Level:** {p['risk_level'].upper()}\n"
                    f"**Automated Execution Available:** {'Yes' if p['execution_available'] else 'No (Manual/CMS)'}\n"
                    f"**Rationale:** {p['reason']}\n\n"
                    f"**Verification Strategy:** {p['verification_plan'].get('criteria', '')}\n\n"
                    f"1. **Human Review:** Review proposed change details.\n"
                    f"2. **Human Approval:** Approve action in dashboard.\n"
                    f"3. **Execution:** Apply change via safe connector.\n"
                    f"4. **Verification:** Inspect live website state."
                )

                action = SEOAction.objects.create(
                    project=self.project,
                    plan=action_plan,
                    title=p['title'],
                    description=p['description'],
                    rationale=p['reason'],
                    evidence_snapshot=p['evidence'],
                    action_type=p['action_type'],
                    target_url=p['target_url'],
                    target_keyword=p.get('target_keyword', ''),
                    current_state=p.get('current_state', {}),
                    proposed_change=p.get('proposed_change', {}),
                    implementation_instructions=instructions,
                    priority=ActionPriority.HIGH if p.get('expected_impact') == 'high' else ActionPriority.MEDIUM,
                    risk_level=p['risk_level'],
                    impact_estimate=p.get('expected_impact', 'medium'),
                    effort_estimate='low' if p['execution_available'] else 'medium',
                    requires_human_approval=True,
                    status=ActionStatus.PROPOSED,
                    verification_status=VerificationStatus.PENDING,
                    verification_result={"verification_plan": p['verification_plan']}
                )
                created_actions.append(action)

        # 3. Emit Agent Events
        self._emit_event(
            AgentEventType.SEO_ACTION_PLAN_CREATED,
            payload={
                "plan_id": action_plan.id,
                "title": action_plan.title,
                "actions_count": len(created_actions),
                "risk_level": action_plan.risk_level,
                "confidence_score": action_plan.confidence_score,
                "requires_human_approval": action_plan.requires_human_approval
            },
            run_id=run_id or (agent_run.id if agent_run else None)
        )

        for act in created_actions:
            self._emit_event(
                AgentEventType.SEO_ACTION_PROPOSED,
                payload={
                    "plan_id": action_plan.id,
                    "action_id": act.id,
                    "action_type": act.action_type,
                    "title": act.title,
                    "target_url": act.target_url,
                    "risk_level": act.risk_level,
                    "requires_human_approval": act.requires_human_approval
                },
                run_id=run_id or (agent_run.id if agent_run else None)
            )

        logger.info(
            f"[SEOActionPlanner] Created SEOActionPlan #{action_plan.id} with {len(created_actions)} actions "
            f"for project #{self.project.id} (Risk: {action_plan.risk_level}, Confidence: {action_plan.confidence_score})."
        )

        return action_plan
