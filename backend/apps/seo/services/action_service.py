import logging
from typing import Optional, Dict, Any
from django.utils import timezone
from apps.projects.models import Project
from apps.seo.models import (
    SEORecommendation, SEOContentBrief, SEOContentDraft, SEOInsight,
    SEOAction, ActionType, ActionStatus, ActionPriority,
    KeywordRanking, SearchAnalyticsData, AuditIssue
)
from .ai_providers import BaseAIProvider, get_ai_provider

logger = logging.getLogger(__name__)

from .agent_events import AgentEventPublisher, AgentEventType, AgentEvent, get_event_publisher

VALID_ACTION_TYPES = set(ActionType.values)
VALID_STATUSES = set(ActionStatus.values)
VALID_PRIORITIES = set(ActionPriority.values)


class SEOActionService:
    """
    SEO Action Generator Service for DoxaRank.
    Converts structured recommendations, content briefs, content drafts, or SEO investigation
    results into actionable, executable SEOAction tasks with clear implementation instructions
    and strict human-in-the-loop approval gating.
    """

    def __init__(
        self,
        project: Project,
        provider: Optional[BaseAIProvider] = None,
        publisher: Optional[AgentEventPublisher] = None
    ):
        self.project = project
        self.provider = provider or get_ai_provider()
        self.publisher = publisher or get_event_publisher()

    def _emit_event(
        self,
        event_type: Any,
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
            logger.debug(f"[SEOActionService] Event emission skipped/failed: {exc}")

    def propose_from_investigation(
        self,
        investigation: Any,
        run_id: Optional[int] = None
    ) -> Optional[SEOAction]:
        """
        Convert an SEOInvestigationResult or investigation dictionary into a structured,
        persistent SEOAction in PENDING_APPROVAL status.
        Preserves empirical facts, inferences, causal root cause, and estimated impact.
        Marks requires_human_approval=True for every mutation action.
        Non-mutating actions (MONITOR, NO_ACTION) do not enter the mutation approval pipeline.
        """
        if hasattr(investigation, 'to_dict'):
            data = investigation.to_dict()
            inv_proj_id = getattr(investigation, 'project_id', self.project.id)
        elif isinstance(investigation, dict):
            data = investigation
            inv_proj_id = data.get('project_id', self.project.id)
        else:
            raise ValueError("Invalid investigation payload: Expected SEOInvestigationResult or dict.")

        if inv_proj_id != self.project.id:
            raise ValueError(f"Investigation belongs to project #{inv_proj_id}, not current project #{self.project.id}.")

        inv_id = data.get('investigation_id', '')
        opp_type = data.get('opportunity_type', '')
        rec_action = data.get('recommended_action') or {}
        raw_action_type = (rec_action.get('action_type') or 'NO_ACTION').upper()

        # Non-mutating actions (MONITOR, NO_ACTION) do not create pending mutation actions
        if raw_action_type in ['MONITOR', 'NO_ACTION']:
            logger.info(f"[SEOActionService] Investigation #{inv_id} resulted in non-mutating action '{raw_action_type}'. No mutation action proposed.")
            return None

        # Normalize action type
        mapped_action_type = raw_action_type.lower()
        if mapped_action_type not in VALID_ACTION_TYPES:
            mapped_action_type = ActionType.OPTIMIZE_EXISTING_CONTENT

        target_url = rec_action.get('target_url') or data.get('target_url') or self.project.website_url
        target_query = rec_action.get('target_query') or data.get('target_query') or ''
        title = rec_action.get('title') or f"Apply {raw_action_type} for {target_url}"
        description = rec_action.get('description') or data.get('root_cause_reason') or 'Automated SEO optimization proposal.'
        rationale = data.get('root_cause_reason') or ''

        # Build evidence snapshot
        evidence_snapshot = {
            "investigation_id": inv_id,
            "opportunity_type": opp_type,
            "root_cause_category": data.get('root_cause_category', 'UNKNOWN'),
            "root_cause_reason": data.get('root_cause_reason', ''),
            "confidence_score": data.get('confidence_score', 0.0),
            "confidence_level": data.get('confidence_level', 'LOW'),
            "observed_facts": data.get('observed_facts', []),
            "inferences": data.get('inferences', []),
            "supporting_gsc_metrics": data.get('supporting_gsc_metrics', {}),
            "supporting_audit_issues": data.get('supporting_audit_issues', [])
        }

        # Build proposed change payload
        proposed_change = rec_action.get('proposed_changes') or {}
        if not proposed_change:
            if 'title' in mapped_action_type:
                proposed_change = {"title": rec_action.get('suggested_title') or title}
            elif 'meta_description' in mapped_action_type:
                proposed_change = {"meta_description": rec_action.get('suggested_description') or description}
            elif 'canonical' in mapped_action_type:
                proposed_change = {"canonical_url": target_url}
            elif 'h1' in mapped_action_type:
                proposed_change = {"h1": title}
            else:
                proposed_change = {"target_url": target_url, "action": raw_action_type}

        # Current state snapshot
        current_state = {
            "target_url": target_url,
            "target_query": target_query,
            "audit_issues": [i.get('issue_type') for i in data.get('supporting_audit_issues', []) if isinstance(i, dict)],
            "gsc_metrics": data.get('supporting_gsc_metrics', {})
        }

        instructions = (
            f"### Proposed Mutation Action: {title}\n\n"
            f"**Target URL:** {target_url}\n"
            f"**Target Query:** {target_query or 'N/A'}\n"
            f"**Causal Root Cause:** {rationale}\n\n"
            f"**1. Human Review:** Review proposed change and confirm accuracy.\n"
            f"**2. Human Approval:** Approve action in DoxaRank dashboard.\n"
            f"**3. Safe Execution:** Apply verified changes via safe mutation connector."
        )

        risk_lvl = str(data.get('risk_level') or 'low').lower()
        impact_est = str(data.get('impact_estimate') or 'medium').lower()
        effort_est = str(data.get('effort_estimate') or 'low').lower()

        # Check existing action for deduplication
        existing = SEOAction.objects.filter(
            project=self.project,
            investigation_id=inv_id
        ).first() if inv_id else None

        if existing:
            action = existing
            action.opportunity_type = opp_type
            action.title = title[:255]
            action.description = description
            action.rationale = rationale
            action.evidence_snapshot = evidence_snapshot
            action.action_type = mapped_action_type
            action.target_url = target_url[:500]
            action.target_keyword = target_query[:255]
            action.current_state = current_state
            action.proposed_change = proposed_change
            action.implementation_instructions = instructions
            action.risk_level = risk_lvl
            action.impact_estimate = impact_est
            action.effort_estimate = effort_est
            action.requires_human_approval = True
            action.status = ActionStatus.PENDING_APPROVAL
            action.save()
        else:
            action = SEOAction.objects.create(
                project=self.project,
                investigation_id=inv_id,
                opportunity_type=opp_type,
                title=title[:255],
                description=description,
                rationale=rationale,
                evidence_snapshot=evidence_snapshot,
                action_type=mapped_action_type,
                target_url=target_url[:500],
                target_keyword=target_query[:255],
                current_state=current_state,
                proposed_change=proposed_change,
                implementation_instructions=instructions,
                priority=ActionPriority.HIGH,
                risk_level=risk_lvl,
                impact_estimate=impact_est,
                effort_estimate=effort_est,
                requires_human_approval=True,
                status=ActionStatus.PENDING_APPROVAL
            )

        logger.info(f"[SEOActionService] Proposed SEOAction #{action.id} ('{action.title}') from Investigation #{inv_id}. Status: PENDING_APPROVAL.")

        self._emit_event(
            AgentEventType.SEO_ACTION_PROPOSED,
            payload={
                "action_id": action.id,
                "investigation_id": inv_id,
                "action_type": action.action_type,
                "title": action.title,
                "target_url": action.target_url,
                "risk_level": action.risk_level,
                "requires_human_approval": True,
                "status": action.status
            },
            run_id=run_id
        )

        self._emit_event(
            AgentEventType.SEO_ACTION_PENDING_APPROVAL,
            payload={
                "action_id": action.id,
                "investigation_id": inv_id,
                "title": action.title,
                "target_url": action.target_url,
                "requires_human_approval": True
            },
            run_id=run_id
        )

        return action

    def generate_for_recommendation(
        self,
        recommendation: SEORecommendation,
        action_type_override: Optional[str] = None
    ) -> SEOAction:
        """
        Generate a structured SEOAction based on an existing recommendation.
        Strictly enforces project ownership.
        """
        if recommendation.project_id != self.project.id:
            raise ValueError(f"Recommendation #{recommendation.id} does not belong to project #{self.project.id}.")

        action_type = action_type_override or self._infer_action_type_from_recommendation(recommendation)
        if action_type not in VALID_ACTION_TYPES:
            action_type = ActionType.OPTIMIZE_EXISTING_CONTENT

        context = self._build_recommendation_action_context(recommendation, action_type)
        raw_action = self.provider.generate_action(context)
        sanitized = self._sanitize_action_payload(raw_action, action_type, default_title=recommendation.title)

        existing = SEOAction.objects.filter(
            project=self.project,
            recommendation=recommendation
        ).first()

        if existing:
            existing.title = sanitized['title']
            existing.description = sanitized['description']
            existing.action_type = sanitized['action_type']
            existing.target_url = sanitized['target_url'] or recommendation.affected_url or self.project.website_url
            existing.target_keyword = sanitized['target_keyword'] or recommendation.affected_keyword
            existing.current_state = sanitized['current_state']
            existing.proposed_change = sanitized['proposed_change']
            existing.implementation_instructions = sanitized['implementation_instructions']
            existing.priority = sanitized['priority']
            existing.save()
            return existing

        action = SEOAction.objects.create(
            project=self.project,
            recommendation=recommendation,
            title=sanitized['title'],
            description=sanitized['description'],
            action_type=sanitized['action_type'],
            target_url=sanitized['target_url'] or recommendation.affected_url or self.project.website_url,
            target_keyword=sanitized['target_keyword'] or recommendation.affected_keyword,
            current_state=sanitized['current_state'],
            proposed_change=sanitized['proposed_change'],
            implementation_instructions=sanitized['implementation_instructions'],
            priority=sanitized['priority'],
            status=ActionStatus.PROPOSED
        )
        return action

    def generate_for_draft(self, draft: SEOContentDraft) -> SEOAction:
        """
        Generate a publishing-ready SEOAction from an SEOContentDraft.
        Produces full publish package payload with schema, FAQs, and metadata.
        """
        if draft.project_id != self.project.id:
            raise ValueError(f"Content Draft #{draft.id} does not belong to project #{self.project.id}.")

        action_type = ActionType.PUBLISH_NEW_CONTENT
        context = self._build_draft_action_context(draft)
        raw_action = self.provider.generate_action(context)
        sanitized = self._sanitize_action_payload(raw_action, action_type, default_title=f"Publish: {draft.title}")

        existing = SEOAction.objects.filter(
            project=self.project,
            draft=draft
        ).first()

        target_url = draft.target_url or draft.suggested_slug or self.project.website_url

        if existing:
            existing.title = sanitized['title']
            existing.description = sanitized['description']
            existing.action_type = sanitized['action_type']
            existing.target_url = sanitized['target_url'] or target_url
            existing.target_keyword = sanitized['target_keyword'] or draft.target_keyword
            existing.current_state = sanitized['current_state']
            existing.proposed_change = sanitized['proposed_change']
            existing.implementation_instructions = sanitized['implementation_instructions']
            existing.priority = sanitized['priority']
            existing.brief = draft.brief
            existing.recommendation = draft.recommendation
            existing.save()
            return existing

        action = SEOAction.objects.create(
            project=self.project,
            draft=draft,
            brief=draft.brief,
            recommendation=draft.recommendation,
            title=sanitized['title'],
            description=sanitized['description'],
            action_type=sanitized['action_type'],
            target_url=sanitized['target_url'] or target_url,
            target_keyword=sanitized['target_keyword'] or draft.target_keyword,
            current_state=sanitized['current_state'],
            proposed_change=sanitized['proposed_change'],
            implementation_instructions=sanitized['implementation_instructions'],
            priority=sanitized['priority'],
            status=ActionStatus.PROPOSED
        )
        return action

    def generate_for_brief(self, brief: SEOContentBrief) -> SEOAction:
        """
        Generate an SEOAction from an SEOContentBrief.
        """
        if brief.project_id != self.project.id:
            raise ValueError(f"Content Brief #{brief.id} does not belong to project #{self.project.id}.")

        action_type = ActionType.PUBLISH_NEW_CONTENT if brief.content_type in ['blog_post', 'landing_page'] else ActionType.OPTIMIZE_EXISTING_CONTENT
        context = {
            "source_type": "brief",
            "action_type": action_type,
            "project_name": self.project.name,
            "website_url": self.project.website_url,
            "brief_id": brief.id,
            "title": brief.title,
            "target_keyword": brief.target_keyword,
            "target_url": brief.target_url or self.project.website_url,
            "priority": ActionPriority.HIGH,
            "current_state": {
                "content_type": brief.content_type,
                "target_keyword": brief.target_keyword
            },
            "proposed_payload": {
                "title": brief.recommended_title or brief.title,
                "slug": brief.suggested_slug,
                "meta_description": brief.meta_description,
                "outline": brief.outline,
                "key_points": brief.key_points,
                "internal_links": brief.internal_link_suggestions,
                "faq": brief.faq_questions
            }
        }
        raw_action = self.provider.generate_action(context)
        sanitized = self._sanitize_action_payload(raw_action, action_type, default_title=brief.title)

        existing = SEOAction.objects.filter(
            project=self.project,
            brief=brief
        ).first()

        target_url = brief.target_url or self.project.website_url

        if existing:
            existing.title = sanitized['title']
            existing.description = sanitized['description']
            existing.action_type = sanitized['action_type']
            existing.target_url = sanitized['target_url'] or target_url
            existing.target_keyword = sanitized['target_keyword'] or brief.target_keyword
            existing.current_state = sanitized['current_state']
            existing.proposed_change = sanitized['proposed_change']
            existing.implementation_instructions = sanitized['implementation_instructions']
            existing.priority = sanitized['priority']
            existing.recommendation = brief.recommendation
            existing.save()
            return existing

        action = SEOAction.objects.create(
            project=self.project,
            brief=brief,
            recommendation=brief.recommendation,
            title=sanitized['title'],
            description=sanitized['description'],
            action_type=sanitized['action_type'],
            target_url=sanitized['target_url'] or target_url,
            target_keyword=sanitized['target_keyword'] or brief.target_keyword,
            current_state=sanitized['current_state'],
            proposed_change=sanitized['proposed_change'],
            implementation_instructions=sanitized['implementation_instructions'],
            priority=sanitized['priority'],
            status=ActionStatus.PROPOSED
        )
        return action

    def _infer_action_type_from_recommendation(self, rec: SEORecommendation) -> str:
        rec_type = rec.recommendation_type
        mapping = {
            'meta_title': ActionType.UPDATE_TITLE,
            'meta_description': ActionType.UPDATE_META_DESCRIPTION,
            'content_update': ActionType.OPTIMIZE_EXISTING_CONTENT,
            'keyword_optimization': ActionType.OPTIMIZE_EXISTING_CONTENT,
            'internal_linking': ActionType.ADD_INTERNAL_LINKS,
            'technical_seo': ActionType.TECHNICAL_SEO_FIX,
            'ranking_recovery': ActionType.OPTIMIZE_EXISTING_CONTENT,
            'ctr_optimization': ActionType.UPDATE_META_DESCRIPTION,
            'page_two_opportunity': ActionType.CONTENT_REFRESH,
            'general_seo': ActionType.OPTIMIZE_EXISTING_CONTENT,
        }
        return mapping.get(rec_type, ActionType.OPTIMIZE_EXISTING_CONTENT)

    def _build_recommendation_action_context(self, rec: SEORecommendation, action_type: str) -> Dict[str, Any]:
        target_keyword = rec.affected_keyword or (rec.insight.related_keyword.keyword if rec.insight.related_keyword else '')
        target_url = rec.affected_url or rec.insight.related_url or self.project.website_url

        # Check ranking position
        pos = None
        if target_keyword:
            rk = KeywordRanking.objects.filter(keyword__project=self.project, keyword__keyword__iexact=target_keyword).order_by('-recorded_at').first()
            if rk:
                pos = rk.position

        current_state = {
            "target_url": target_url,
            "target_keyword": target_keyword,
            "current_ranking_position": pos,
            "insight_severity": rec.insight.severity,
            "insight_title": rec.insight.title,
            "recommendation_summary": rec.summary
        }

        generated_copy = rec.generated_content or {}
        proposed_payload = {
            "title": generated_copy.get('proposed_title', ''),
            "meta_description": generated_copy.get('proposed_meta_description', ''),
            "action_checklist": generated_copy.get('action_checklist', []),
            "content_suggestions": generated_copy.get('content_suggestions', ''),
            "recommended_action": rec.recommended_action
        }

        return {
            "source_type": "recommendation",
            "action_type": action_type,
            "project_name": self.project.name,
            "website_url": self.project.website_url,
            "recommendation_id": rec.id,
            "title": rec.title,
            "priority": rec.priority,
            "target_url": target_url,
            "target_keyword": target_keyword,
            "current_state": current_state,
            "proposed_payload": proposed_payload
        }

    def _build_draft_action_context(self, draft: SEOContentDraft) -> Dict[str, Any]:
        target_url = draft.target_url or draft.suggested_slug or self.project.website_url

        publishing_package = {
            "title": draft.title,
            "slug": draft.suggested_slug,
            "meta_title": draft.meta_title or draft.title,
            "meta_description": draft.meta_description,
            "content": draft.content_body,
            "faq": draft.faq_section or [],
            "internal_links": draft.internal_links or [],
            "external_links": draft.external_links or [],
            "schema_json_ld": draft.schema_json_ld or {},
            "target_keyword": draft.target_keyword,
            "secondary_keywords": draft.secondary_keywords or [],
            "word_count": draft.word_count,
            "content_type": draft.content_type
        }

        current_state = {
            "target_url": target_url,
            "target_keyword": draft.target_keyword,
            "word_count": draft.word_count,
            "draft_status": draft.status
        }

        return {
            "source_type": "draft",
            "action_type": ActionType.PUBLISH_NEW_CONTENT,
            "project_name": self.project.name,
            "website_url": self.project.website_url,
            "draft_id": draft.id,
            "title": f"Publish: {draft.title}",
            "priority": ActionPriority.HIGH,
            "target_url": target_url,
            "target_keyword": draft.target_keyword,
            "current_state": current_state,
            "proposed_payload": publishing_package
        }

    def _sanitize_action_payload(
        self,
        raw: Dict[str, Any],
        fallback_action_type: str,
        default_title: str
    ) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            raw = {}

        title = str(raw.get('title') or default_title or 'SEO Action Proposal').strip()[:255]
        description = str(raw.get('description') or 'Actionable SEO task generated from grounded evidence.').strip()
        
        action_type = raw.get('action_type')
        if action_type not in VALID_ACTION_TYPES:
            action_type = fallback_action_type

        priority = raw.get('priority')
        if priority not in VALID_PRIORITIES:
            priority = ActionPriority.HIGH

        target_url = str(raw.get('target_url') or '').strip()[:500]
        target_keyword = str(raw.get('target_keyword') or '').strip()[:255]

        current_state = raw.get('current_state')
        if not isinstance(current_state, dict):
            current_state = {"summary": str(current_state or '')}

        proposed_change = raw.get('proposed_change')
        if not isinstance(proposed_change, dict):
            proposed_change = {"proposal": str(proposed_change or '')}

        instructions = str(raw.get('implementation_instructions') or '').strip()
        if not instructions:
            instructions = (
                "### Implementation Instructions\n\n"
                "**1. Marketer:** Review proposed changes and copy alignment.\n"
                "**2. SEO Specialist:** Verify keyword density and search intent.\n"
                "**3. Developer:** Deploy approved changes to production."
            )

        return {
            "title": title,
            "description": description,
            "action_type": action_type,
            "priority": priority,
            "target_url": target_url,
            "target_keyword": target_keyword,
            "current_state": current_state,
            "proposed_change": proposed_change,
            "implementation_instructions": instructions
        }
