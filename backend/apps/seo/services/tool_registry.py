"""
DoxaRank Tool Registry & Schema Abstraction Layer.

Provides a centralized, provider-neutral, JSON-Schema-driven registry of all
agent-callable tools in DoxaRank. Ensures strict multi-tenant isolation, argument
validation, and safety governance boundaries.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Tuple

from apps.projects.models import Project
from apps.seo.models import (
    Keyword, KeywordRanking, SiteAudit, AuditIssue,
    AuditStatus, IssueSeverity,
    SearchAnalyticsData, SEOInsight, SEORecommendation,
    SEOContentBrief, SEOContentDraft, SEOAction, SEOActionPlan,
    ActionType, ActionStatus, ActionPriority, ActionPlanStatus,
    ActionRiskLevel, VerificationStatus,
    BriefContentType, BriefSearchIntent
)
from apps.seo.services.seo_intelligence import SEOIntelligenceService
from apps.seo.services.ai_seo_agent import AISeoAgentService
from apps.seo.services.content_brief_service import SEOContentBriefService
from apps.seo.services.content_writer_service import SEOContentWriterService
from apps.seo.services.action_service import SEOActionService

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    READ_ONLY = 'read_only'
    SAFE_INTERNAL = 'safe_internal'
    HIGH_IMPACT = 'high_impact'


@dataclass
class AgentToolDefinition:
    """
    Metadata and execution specification for an agent-callable tool.
    Designed for provider neutrality and future MCP compatibility.
    """
    name: str
    description: str
    category: ToolCategory
    parameters_schema: Dict[str, Any]
    requires_approval: bool
    is_mutating: bool
    handler: Callable[[Project, Dict[str, Any]], Dict[str, Any]]

    def to_schema(self) -> Dict[str, Any]:
        """
        Export provider-neutral tool schema for LLM function/tool declaration.
        """
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value if isinstance(self.category, ToolCategory) else self.category,
            "parameters": self.parameters_schema,
            "requires_approval": self.requires_approval,
            "is_mutating": self.is_mutating
        }


class ToolRegistry:
    """
    Central registry for discovering, validating, and safely invoking agent tools.
    Strictly guarantees tenant isolation by requiring explicit Project context.
    """

    def __init__(self):
        self._tools: Dict[str, AgentToolDefinition] = {}

    def register(self, tool: AgentToolDefinition) -> None:
        """Register a new tool definition in the registry."""
        if tool.name in self._tools:
            logger.warning(f"Overwriting existing tool registration: '{tool.name}'")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[AgentToolDefinition]:
        """Retrieve tool definition by name, returning None if not found."""
        return self._tools.get(name)

    def get_tool(self, name: str) -> AgentToolDefinition:
        """Retrieve tool definition by name, raising KeyError if not found."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered in ToolRegistry.")
        return self._tools[name]

    def list_tools(self) -> List[AgentToolDefinition]:
        """Return list of all registered tool definitions."""
        return list(self._tools.values())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Return list of schemas suitable for LLM tool declaration."""
        return [tool.to_schema() for tool in self._tools.values()]

    def validate_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validates argument types and required fields against declared parameter schema.
        Returns (is_valid, error_message).
        """
        tool = self.get(tool_name)
        if not tool:
            return False, f"Tool '{tool_name}' is not registered."

        if not isinstance(arguments, dict):
            return False, f"Tool arguments must be a dictionary, got {type(arguments).__name__}."

        schema = tool.parameters_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Check required fields
        for req_field in required:
            if req_field not in arguments:
                return False, f"Missing required parameter '{req_field}' for tool '{tool_name}'."
            if arguments[req_field] is None:
                return False, f"Required parameter '{req_field}' cannot be null for tool '{tool_name}'."

        # Check types for present fields
        for key, value in arguments.items():
            if key not in properties:
                # Disallow unexpected injected fields to prevent tampering
                continue

            prop_spec = properties[key]
            expected_type = prop_spec.get("type")
            enum_values = prop_spec.get("enum")

            if value is not None and expected_type:
                if expected_type == "string" and not isinstance(value, str):
                    return False, f"Parameter '{key}' must be a string, got {type(value).__name__}."
                elif expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                    return False, f"Parameter '{key}' must be an integer, got {type(value).__name__}."
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    return False, f"Parameter '{key}' must be a number, got {type(value).__name__}."
                elif expected_type == "boolean" and not isinstance(value, bool):
                    return False, f"Parameter '{key}' must be a boolean, got {type(value).__name__}."
                elif expected_type == "array" and not isinstance(value, list):
                    return False, f"Parameter '{key}' must be an array, got {type(value).__name__}."
                elif expected_type == "object" and not isinstance(value, dict):
                    return False, f"Parameter '{key}' must be an object, got {type(value).__name__}."

            if enum_values and value is not None and value not in enum_values:
                return False, f"Parameter '{key}' value '{value}' is not in allowed values: {enum_values}."

        return True, None

    def execute(self, tool_name: str, project: Project, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a registered tool against an authorized Project context.
        Returns a standardized execution result dictionary.
        """
        start_time = time.time()
        args = arguments or {}

        # 1. Check Tool Existence
        tool = self.get(tool_name)
        if not tool:
            return {
                "success": False,
                "tool_name": tool_name,
                "data": None,
                "duration_ms": 0,
                "is_mutating": False,
                "requires_approval": False,
                "error": {
                    "code": "TOOL_NOT_FOUND",
                    "message": f"Tool '{tool_name}' is not registered."
                }
            }

        # 2. Validate Arguments Against Schema
        is_valid, validation_error = self.validate_arguments(tool_name, args)
        if not is_valid:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "tool_name": tool_name,
                "data": None,
                "duration_ms": duration_ms,
                "is_mutating": tool.is_mutating,
                "requires_approval": tool.requires_approval,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": validation_error
                }
            }

        # 3. Execute Handler with Explicit Project Context
        try:
            result_data = tool.handler(project, args)
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "success": True,
                "tool_name": tool_name,
                "data": result_data,
                "duration_ms": duration_ms,
                "is_mutating": tool.is_mutating,
                "requires_approval": tool.requires_approval,
                "error": None
            }
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.exception(f"Error executing agent tool '{tool_name}' on project #{project.id}: {exc}")
            safe_error_msg = _sanitize_error_message(str(exc))
            return {
                "success": False,
                "tool_name": tool_name,
                "data": None,
                "duration_ms": duration_ms,
                "is_mutating": tool.is_mutating,
                "requires_approval": tool.requires_approval,
                "error": {
                    "code": "EXECUTION_ERROR",
                    "message": safe_error_msg
                }
            }


def _sanitize_error_message(message: str) -> str:
    """Sanitize error messages to prevent accidental leakage of API keys or credentials."""
    if not message:
        return ""
    import re
    # Mask OpenAI-style keys (sk-...) and generic auth tokens
    clean = re.sub(r'sk-[a-zA-Z0-9_-]{8,}', 'sk-***', message)
    clean = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]{8,}', 'Bearer ***', clean, flags=re.IGNORECASE)
    return clean[:500]


# ==============================================================================
# TOOL HANDLERS (Wrapping Existing DoxaRank Services & Querysets)
# ==============================================================================

def handle_get_keyword_rankings(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve keyword ranking data for the project."""
    keyword_filter = args.get("keyword")
    search_engine = args.get("search_engine")
    country = args.get("country")
    limit = min(args.get("limit", 20), 100)

    qs = Keyword.objects.filter(project=project)
    if keyword_filter:
        qs = qs.filter(keyword__icontains=keyword_filter)
    if search_engine:
        qs = qs.filter(search_engine=search_engine)
    if country:
        qs = qs.filter(country=country)

    results = []
    for kw in qs[:limit]:
        latest_ranking = kw.rankings.order_by('-recorded_at').first()
        results.append({
            "keyword_id": kw.id,
            "keyword": kw.keyword,
            "search_engine": kw.search_engine,
            "country": kw.country,
            "device": kw.device,
            "current_position": latest_ranking.position if latest_ranking else None,
            "ranking_url": latest_ranking.ranking_url if latest_ranking else None,
            "recorded_at": latest_ranking.recorded_at.isoformat() if latest_ranking else None
        })

    return {
        "project_id": project.id,
        "total_keywords": qs.count(),
        "returned_count": len(results),
        "rankings": results
    }


def handle_get_search_console_analytics(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve Search Console performance metrics for the project."""
    query_filter = args.get("query")
    min_impressions = args.get("min_impressions", 0)
    max_ctr_percent = args.get("max_ctr_percent")
    limit = min(args.get("limit", 20), 100)

    qs = SearchAnalyticsData.objects.filter(connection__project=project)
    if query_filter:
        qs = qs.filter(query__icontains=query_filter)
    if min_impressions > 0:
        qs = qs.filter(impressions__gte=min_impressions)
    if max_ctr_percent is not None:
        qs = qs.filter(ctr__lte=max_ctr_percent / 100.0)

    qs = qs.order_by('-impressions')[:limit]

    items = []
    for row in qs:
        items.append({
            "query": row.query,
            "page": row.page,
            "clicks": row.clicks,
            "impressions": row.impressions,
            "ctr_percent": round(row.ctr * 100, 2),
            "position": round(row.position, 1),
            "device": row.device,
            "country": row.country,
            "date": row.date.isoformat() if row.date else None
        })

    return {
        "project_id": project.id,
        "returned_count": len(items),
        "analytics": items
    }


def handle_trigger_site_audit(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger an asynchronous website crawl and technical SEO audit for the current project.

    Guarantees:
    - Safe crawler limit bounding (max_pages 1..200, max_depth 0..10).
    - Start URL validation ensuring it belongs to the project domain.
    - Non-blocking asynchronous Celery dispatch.
    - Strict multi-tenant context enforcement.
    """
    if not project.website_url:
        raise ValueError(f"Project #{project.id} ('{project.name}') has no configured website_url.")

    start_url = args.get("start_url")
    raw_pages = args.get("max_pages", 50)
    raw_depth = args.get("max_depth", 3)

    try:
        max_pages = max(1, min(int(raw_pages), 200))
    except (ValueError, TypeError):
        max_pages = 50

    try:
        max_depth = max(0, min(int(raw_depth), 10))
    except (ValueError, TypeError):
        max_depth = 3

    target_url = start_url.strip() if (start_url and isinstance(start_url, str)) else project.website_url

    from apps.seo.services.live_site_crawler import LiveSiteCrawlerService
    if not LiveSiteCrawlerService.is_same_domain(project.website_url, target_url):
        raise ValueError(
            f"Provided start_url '{target_url}' does not belong to project website domain '{project.website_url}'."
        )

    # Create SiteAudit in PENDING status
    audit = SiteAudit.objects.create(
        project=project,
        status=AuditStatus.PENDING
    )

    from apps.seo.tasks import run_site_audit
    task_res = run_site_audit.delay(
        audit_id=audit.id,
        start_url=target_url,
        max_pages=max_pages,
        max_depth=max_depth
    )

    return {
        "success": True,
        "audit_id": audit.id,
        "project_id": project.id,
        "status": "queued",
        "start_url": target_url,
        "max_pages": max_pages,
        "max_depth": max_depth,
        "task_id": str(task_res.id) if hasattr(task_res, 'id') else None,
        "message": f"SEO live site audit #{audit.id} queued successfully for {target_url}."
    }


def handle_get_site_audit_summary(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve a compact, structured summary of the latest or specified site audit for the project.

    Guarantees:
    - Compact, LLM-optimized summary (health score, issue counts by severity, top issue types).
    - Strict multi-tenant isolation.
    - Graceful handling of non-existent, pending, running, or failed audits.
    """
    from django.db.models import Count

    audit_id = args.get("audit_id")
    if audit_id:
        try:
            audit = SiteAudit.objects.filter(project=project, id=audit_id).first()
        except (ValueError, TypeError):
            audit = None
        if not audit:
            return {
                "audit_id": audit_id,
                "project_id": project.id,
                "status": "not_found",
                "message": f"SiteAudit #{audit_id} not found on project #{project.id}."
            }
    else:
        audit = SiteAudit.objects.filter(project=project).order_by('-created_at').first()
        if not audit:
            return {
                "audit_id": None,
                "project_id": project.id,
                "status": "not_found",
                "message": f"No site audits found for project #{project.id}."
            }

    critical_count = audit.issues.filter(severity=IssueSeverity.CRITICAL).count()
    warning_count = audit.issues.filter(severity=IssueSeverity.WARNING).count()
    notice_count = audit.issues.filter(severity=IssueSeverity.NOTICE).count()

    top_issue_groups = (
        audit.issues.values('issue_type', 'severity')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )
    top_issues = [
        {
            "rule_code": g['issue_type'],
            "severity": g['severity'],
            "count": g['count']
        }
        for g in top_issue_groups
    ]

    pages_with_issues = audit.issues.values('page_url').distinct().count()

    return {
        "audit_id": audit.id,
        "project_id": project.id,
        "status": audit.status,
        "health_score": audit.score,
        "started_at": audit.started_at.isoformat() if audit.started_at else None,
        "completed_at": audit.completed_at.isoformat() if audit.completed_at else None,
        "error_message": audit.error_message,
        "total_issues": critical_count + warning_count + notice_count,
        "issues_by_severity": {
            "critical": critical_count,
            "warning": warning_count,
            "notice": notice_count
        },
        "pages_with_issues_count": pages_with_issues,
        "top_issues": top_issues
    }


def handle_get_audit_issues(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve site audit technical SEO issues with optional filtering."""
    audit_id = args.get("audit_id")
    severity = args.get("severity")
    issue_type = args.get("issue_type")
    page_url = args.get("page_url")

    raw_limit = args.get("limit", 20)
    try:
        limit = min(max(1, int(raw_limit)), 100)
    except (ValueError, TypeError):
        limit = 20

    qs = AuditIssue.objects.filter(audit__project=project)
    if audit_id:
        qs = qs.filter(audit_id=audit_id)
    if severity:
        sev = str(severity).lower()
        if sev == 'info':
            sev = IssueSeverity.NOTICE
        qs = qs.filter(severity=sev)
    if issue_type:
        qs = qs.filter(issue_type=issue_type)
    if page_url:
        qs = qs.filter(page_url__icontains=page_url)

    qs = qs.order_by('-created_at')[:limit]

    issues = []
    for issue in qs:
        issues.append({
            "id": issue.id,
            "audit_id": issue.audit_id,
            "issue_type": issue.issue_type,
            "severity": issue.severity,
            "title": issue.title,
            "description": issue.description,
            "page_url": issue.page_url,
            "recommendation": issue.recommendation,
            "created_at": issue.created_at.isoformat() if issue.created_at else None
        })

    return {
        "project_id": project.id,
        "returned_count": len(issues),
        "issues": issues
    }


def handle_run_intelligence_analysis(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Run the deterministic SEO intelligence heuristic engine."""
    service = SEOIntelligenceService(project=project)
    summary = service.analyze()
    return {
        "project_id": project.id,
        "summary": summary
    }


def handle_generate_recommendation(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an AI recommendation for an insight."""
    insight_id = args.get("insight_id")
    try:
        insight = SEOInsight.objects.get(id=insight_id, project=project)
    except SEOInsight.DoesNotExist:
        raise ValueError(f"SEOInsight #{insight_id} not found on project #{project.id}.")

    service = AISeoAgentService(project=project)
    rec = service.generate_for_insight(insight)

    return {
        "id": rec.id,
        "insight_id": rec.insight_id,
        "project_id": project.id,
        "recommendation_type": rec.recommendation_type,
        "priority": rec.priority,
        "title": rec.title,
        "summary": rec.summary,
        "explanation": rec.explanation,
        "recommended_action": rec.recommended_action,
        "expected_impact": rec.expected_impact,
        "affected_url": rec.affected_url,
        "affected_keyword": rec.affected_keyword,
        "generated_content": rec.generated_content,
        "status": rec.status
    }


def handle_generate_content_brief(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an SEO content brief from an existing recommendation."""
    recommendation_id = args.get("recommendation_id")
    content_type = args.get("content_type")

    try:
        recommendation = SEORecommendation.objects.get(id=recommendation_id, project=project)
    except SEORecommendation.DoesNotExist:
        raise ValueError(f"SEORecommendation #{recommendation_id} not found on project #{project.id}.")

    service = SEOContentBriefService(project=project)
    brief = service.generate_for_recommendation(recommendation, content_type_override=content_type)

    return {
        "id": brief.id,
        "recommendation_id": brief.recommendation_id,
        "project_id": project.id,
        "title": brief.title,
        "target_keyword": brief.target_keyword,
        "secondary_keywords": brief.secondary_keywords,
        "search_intent": brief.search_intent,
        "content_type": brief.content_type,
        "target_url": brief.target_url,
        "recommended_title": brief.recommended_title,
        "meta_description": brief.meta_description,
        "suggested_slug": brief.suggested_slug,
        "outline": brief.outline,
        "faq_questions": brief.faq_questions,
        "content_length_target": brief.content_length_target,
        "status": brief.status
    }


def handle_generate_content_draft(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an SEO content draft from an existing content brief."""
    content_brief_id = args.get("content_brief_id")
    regenerate = bool(args.get("regenerate", False))

    try:
        brief = SEOContentBrief.objects.get(id=content_brief_id, project=project)
    except SEOContentBrief.DoesNotExist:
        raise ValueError(f"SEOContentBrief #{content_brief_id} not found on project #{project.id}.")

    draft = SEOContentWriterService.generate_for_brief(
        project=project,
        brief=brief,
        regenerate=regenerate
    )

    return {
        "id": draft.id,
        "brief_id": draft.brief_id,
        "project_id": project.id,
        "title": draft.title,
        "meta_title": draft.meta_title,
        "meta_description": draft.meta_description,
        "suggested_slug": draft.suggested_slug,
        "word_count": draft.word_count,
        "keyword_usage": draft.keyword_usage,
        "schema_json_ld": draft.schema_json_ld,
        "content_type": draft.content_type,
        "status": draft.status
    }


def handle_propose_seo_action(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate an SEOAction proposal in 'pending_approval' state.
    Strictly requires human approval before any future execution.
    """
    source_type = args.get("source_type")
    source_id = args.get("source_id")
    action_type_override = args.get("action_type_override")
    investigation_id = args.get("investigation_id")
    opportunity_type = args.get("opportunity_type")
    target_url = args.get("target_url")
    target_query = args.get("target_query")

    action_service = SEOActionService(project=project)

    if source_type == "investigation" or investigation_id or (opportunity_type and not source_id):
        if not opportunity_type and not investigation_id:
            raise ValueError("Must provide either opportunity_type or investigation_id when source_type='investigation'.")

        from apps.seo.services.seo_investigation import SEOInvestigationService
        inv_service = SEOInvestigationService(project=project)
        inv_result = inv_service.investigate(
            opportunity_type=opportunity_type or "LOW_CTR_HIGH_IMPRESSIONS",
            target_url=target_url,
            target_query=target_query
        )
        action = action_service.propose_from_investigation(inv_result)
        if not action:
            return {
                "success": True,
                "proposed": False,
                "message": f"Investigation resulted in non-mutating action '{inv_result.recommended_action.get('action_type')}'. No mutation action proposed.",
                "requires_human_approval": False
            }
    elif source_type == "recommendation":
        try:
            rec = SEORecommendation.objects.get(id=source_id, project=project)
        except SEORecommendation.DoesNotExist:
            raise ValueError(f"SEORecommendation #{source_id} not found on project #{project.id}.")
        action = action_service.generate_for_recommendation(rec, action_type_override=action_type_override)
    elif source_type == "draft":
        try:
            draft = SEOContentDraft.objects.get(id=source_id, project=project)
        except SEOContentDraft.DoesNotExist:
            raise ValueError(f"SEOContentDraft #{source_id} not found on project #{project.id}.")
        action = action_service.generate_for_draft(draft)
    elif source_type == "brief":
        try:
            brief = SEOContentBrief.objects.get(id=source_id, project=project)
        except SEOContentBrief.DoesNotExist:
            raise ValueError(f"SEOContentBrief #{source_id} not found on project #{project.id}.")
        action = action_service.generate_for_brief(brief)
    else:
        raise ValueError(f"Invalid source_type '{source_type}'. Allowed values: ['investigation', 'recommendation', 'draft', 'brief'].")

    return {
        "id": action.id,
        "project_id": project.id,
        "action_type": action.action_type,
        "title": action.title,
        "description": action.description,
        "status": action.status,
        "priority": action.priority,
        "target_keyword": action.target_keyword,
        "target_url": action.target_url,
        "assigned_to": action.assigned_to,
        "proposed_change": action.proposed_change,
        "requires_human_approval": action.requires_human_approval,
        "risk_level": action.risk_level,
        "impact_estimate": action.impact_estimate,
        "effort_estimate": action.effort_estimate
    }


def handle_get_pending_actions(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve all pending SEO actions requiring human review and approval."""
    limit = args.get("limit", 20)
    qs = SEOAction.objects.filter(
        project=project,
        status__in=[ActionStatus.PENDING_APPROVAL, ActionStatus.PROPOSED, ActionStatus.REVIEWED]
    ).order_by('-created_at')[:limit]

    items = [
        {
            "id": a.id,
            "title": a.title,
            "action_type": a.action_type,
            "target_url": a.target_url,
            "status": a.status,
            "risk_level": a.risk_level,
            "impact_estimate": a.impact_estimate,
            "requires_human_approval": a.requires_human_approval,
            "created_at": a.created_at.isoformat()
        }
        for a in qs
    ]
    return {
        "project_id": project.id,
        "total_pending": len(items),
        "actions": items
    }


def handle_get_action(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve detailed state of a single SEO action by ID."""
    action_id = args.get("action_id")
    try:
        a = SEOAction.objects.get(id=action_id, project=project)
    except SEOAction.DoesNotExist:
        raise ValueError(f"SEOAction #{action_id} not found on project #{project.id}.")

    return {
        "id": a.id,
        "project_id": project.id,
        "investigation_id": a.investigation_id,
        "opportunity_type": a.opportunity_type,
        "title": a.title,
        "description": a.description,
        "rationale": a.rationale,
        "action_type": a.action_type,
        "target_url": a.target_url,
        "target_keyword": a.target_keyword,
        "current_state": a.current_state,
        "proposed_change": a.proposed_change,
        "implementation_instructions": a.implementation_instructions,
        "status": a.status,
        "risk_level": a.risk_level,
        "impact_estimate": a.impact_estimate,
        "effort_estimate": a.effort_estimate,
        "requires_human_approval": a.requires_human_approval,
        "approved_by_id": a.approved_by_id,
        "approved_at": a.approved_at.isoformat() if a.approved_at else None,
        "rejected_at": a.rejected_at.isoformat() if a.rejected_at else None,
        "rejection_reason": a.rejection_reason,
        "execution_metadata": a.execution_metadata,
        "created_at": a.created_at.isoformat()
    }


def handle_preview_action(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a safe, non-destructive visual diff preview for an SEOAction."""
    action_id = args.get("action_id")
    try:
        a = SEOAction.objects.get(id=action_id, project=project)
    except SEOAction.DoesNotExist:
        raise ValueError(f"SEOAction #{action_id} not found on project #{project.id}.")

    from apps.seo.services.mutation_connectors import get_mutation_connector
    connector = get_mutation_connector("dry_run")
    preview_data = connector.preview(a)
    return {
        "action_id": a.id,
        "preview": preview_data,
        "status": a.status,
        "requires_human_approval": a.requires_human_approval
    }


def handle_gsc_search_analytics(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Query live Google Search Console performance metrics for the project."""
    from apps.seo.services.google_search_console import GoogleSearchConsoleService
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    dimensions = args.get("dimensions")
    row_limit = args.get("row_limit", 25)
    query_filter = args.get("query_filter")
    page_filter = args.get("page_filter")
    site_url = args.get("site_url")

    dimension_filter_groups = None
    filters = []
    if query_filter and isinstance(query_filter, str) and query_filter.strip():
        filters.append({
            "dimension": "query",
            "operator": "contains",
            "expression": query_filter.strip()
        })
    if page_filter and isinstance(page_filter, str) and page_filter.strip():
        filters.append({
            "dimension": "page",
            "operator": "contains",
            "expression": page_filter.strip()
        })
    if filters:
        dimension_filter_groups = [{"filters": filters}]

    service = GoogleSearchConsoleService(project=project)
    return service.query_search_analytics(
        start_date=start_date,
        end_date=end_date,
        dimensions=dimensions,
        row_limit=row_limit,
        dimension_filter_groups=dimension_filter_groups,
        site_url=site_url
    )


def handle_gsc_top_queries(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve highest performing search queries from Google Search Console."""
    from apps.seo.services.google_search_console import GoogleSearchConsoleService
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    limit = args.get("limit", 20)
    page_filter = args.get("page_filter")

    service = GoogleSearchConsoleService(project=project)
    return service.get_top_queries(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        page_filter=page_filter
    )


def handle_gsc_top_pages(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve highest traffic landing pages from Google Search Console."""
    from apps.seo.services.google_search_console import GoogleSearchConsoleService
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    limit = args.get("limit", 20)
    query_filter = args.get("query_filter")

    service = GoogleSearchConsoleService(project=project)
    return service.get_top_pages(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        query_filter=query_filter
    )


def handle_gsc_opportunity_audit(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute GSC intelligence heuristics across query and page data to detect actionable SEO opportunities."""
    from apps.seo.services.gsc_intelligence import GSCIntelligenceService
    min_impressions = args.get("min_impressions", 10)
    sync_to_insights = bool(args.get("sync_to_insights", True))

    service = GSCIntelligenceService(project=project)
    results = service.analyze_opportunities(min_impressions=min_impressions)

    if sync_to_insights and results.get("findings"):
        persisted = service.sync_findings_to_insights(results["findings"])
        results["persisted_insights_count"] = len(persisted)

    return results


def handle_gsc_performance_comparison(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Compare search performance across two date ranges to analyze trends and traffic movements."""
    from apps.seo.services.gsc_intelligence import GSCIntelligenceService
    base_start = args.get("base_start_date")
    base_end = args.get("base_end_date")
    comp_start = args.get("comp_start_date")
    comp_end = args.get("comp_end_date")
    row_limit = args.get("row_limit", 50)

    service = GSCIntelligenceService(project=project)
    return service.compare_periods(
        base_start=base_start,
        base_end=base_end,
        comp_start=comp_start,
        comp_end=comp_end,
        row_limit=row_limit
    )


def handle_analyze_seo_opportunities(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Correlate Google Search Console search performance data with live website audit diagnostics
    to identify prioritized, deterministic SEO opportunities.
    """
    from apps.seo.services.seo_intelligence import SEOCorrelationIntelligenceService

    min_impressions = args.get("min_impressions", 20)
    limit = args.get("limit", 10)
    page_filter = args.get("page_filter")
    audit_id = args.get("audit_id")
    sync_to_insights = bool(args.get("sync_to_insights", False))

    service = SEOCorrelationIntelligenceService(project=project)
    return service.analyze_correlated_opportunities(
        audit_id=audit_id,
        min_impressions=min_impressions,
        limit=limit,
        page_filter=page_filter,
        sync_to_insights=sync_to_insights
    )


def handle_investigate_seo_opportunity(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Autonomously investigate a specific SEO opportunity by collecting multi-source empirical evidence
    from Search Console and Site Audit diagnostics, classifying root causes, and formulating structured recommendations.
    """
    from apps.seo.services.seo_investigation import SEOInvestigationService

    opportunity_type = args.get("opportunity_type", "")
    target_url = args.get("target_url")
    target_query = args.get("target_query")
    audit_id = args.get("audit_id")
    date_range_days = args.get("date_range_days", 28)

    service = SEOInvestigationService(project=project)
    result = service.investigate(
        opportunity_type=opportunity_type,
        target_url=target_url,
        target_query=target_query,
        audit_id=audit_id,
        date_range_days=date_range_days
    )
    return result.to_dict()


def handle_plan_seo_actions(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synthesize project evidence into a cohesive SEOActionPlan with deterministic
    risk classification, confidence scoring, and deduplicated child action proposals.
    """
    from apps.seo.services.seo_action_planner import SEOActionPlanner
    title = args.get("title")
    summary = args.get("summary")
    audit_id = args.get("audit_id")
    max_actions = args.get("max_actions", 10)

    planner = SEOActionPlanner(project=project)
    plan = planner.create_action_plan(
        title=title,
        summary=summary,
        audit_id=audit_id,
        max_actions=max_actions
    )

    actions = [
        {
            "id": a.id,
            "action_type": a.action_type,
            "title": a.title,
            "target_url": a.target_url,
            "risk_level": a.risk_level,
            "impact_estimate": a.impact_estimate,
            "requires_human_approval": a.requires_human_approval,
            "status": a.status
        }
        for a in plan.actions.all()
    ]

    return {
        "id": plan.id,
        "plan_id": plan.id,
        "title": plan.title,
        "summary": plan.summary,
        "status": plan.status,
        "risk_level": plan.risk_level,
        "confidence_score": plan.confidence_score,
        "total_actions": len(actions),
        "actions": actions,
        "requires_human_approval": plan.requires_human_approval,
        "created_at": plan.created_at.isoformat()
    }


def handle_get_action_plan(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve detailed state of an SEOActionPlan and all child actions."""
    plan_id = args.get("plan_id")
    try:
        plan = SEOActionPlan.objects.prefetch_related('actions').get(id=plan_id, project=project)
    except SEOActionPlan.DoesNotExist:
        raise ValueError(f"SEOActionPlan #{plan_id} not found on project #{project.id}.")

    actions = [
        {
            "id": a.id,
            "action_type": a.action_type,
            "title": a.title,
            "description": a.description,
            "rationale": a.rationale,
            "target_url": a.target_url,
            "risk_level": a.risk_level,
            "impact_estimate": a.impact_estimate,
            "status": a.status,
            "verification_status": a.verification_status,
            "requires_human_approval": a.requires_human_approval
        }
        for a in plan.actions.all()
    ]

    return {
        "id": plan.id,
        "project_id": project.id,
        "title": plan.title,
        "summary": plan.summary,
        "status": plan.status,
        "risk_level": plan.risk_level,
        "confidence_score": plan.confidence_score,
        "requires_human_approval": plan.requires_human_approval,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "rejected_at": plan.rejected_at.isoformat() if plan.rejected_at else None,
        "rejection_reason": plan.rejection_reason,
        "verification_status": plan.verification_status,
        "verification_results": plan.verification_results,
        "total_actions": len(actions),
        "actions": actions,
        "created_at": plan.created_at.isoformat()
    }


def handle_verify_seo_action(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Empirically verify the real-world outcome of an executed SEOAction."""
    action_id = args.get("action_id")
    try:
        action = SEOAction.objects.get(id=action_id, project=project)
    except SEOAction.DoesNotExist:
        raise ValueError(f"SEOAction #{action_id} not found on project #{project.id}.")

    from apps.seo.services.seo_action_verifier import SEOActionVerifier
    verifier = SEOActionVerifier(project=project)
    return verifier.verify_action(action)


def handle_verify_action_plan(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Empirically verify all actions in an SEOActionPlan."""
    plan_id = args.get("plan_id")
    try:
        plan = SEOActionPlan.objects.get(id=plan_id, project=project)
    except SEOActionPlan.DoesNotExist:
        raise ValueError(f"SEOActionPlan #{plan_id} not found on project #{project.id}.")

    from apps.seo.services.seo_action_verifier import SEOActionVerifier
    verifier = SEOActionVerifier(project=project)
    return verifier.verify_plan(plan)


def handle_get_action_outcomes(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve aggregated historical SEO action outcomes, improvement rates, and before/after evidence."""
    action_type = args.get("action_type")
    target_url = args.get("target_url")
    outcome_filter = args.get("outcome")
    limit = min(args.get("limit", 20), 50)

    from apps.seo.services.seo_outcome_learning import SEOHistoricalLearningService
    return SEOHistoricalLearningService.get_historical_outcome_signals(
        project=project,
        action_type=action_type,
        target_url=target_url,
        outcome_filter=outcome_filter,
        limit=limit
    )


def handle_get_adaptive_seo_strategy(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve calibrated adaptive SEO strategy, historical effectiveness, and action prioritization signals."""
    action_type = args.get("action_type")
    from apps.seo.services.seo_adaptive_strategy import SEOAdaptiveStrategyService
    service = SEOAdaptiveStrategyService(project=project)
    strategy = service.evaluate_strategy(action_type_filter=action_type)

    # Return compact, token-efficient response suitable for LLM reasoning
    return {
        "strategy_confidence": strategy.get("strategy_confidence", "none"),
        "historical_sample_size": strategy.get("historical_sample_size", 0),
        "evaluatable_sample_size": strategy.get("evaluatable_sample_size", 0),
        "preferred_actions": strategy.get("preferred_actions", []),
        "deprioritized_actions": strategy.get("deprioritized_actions", []),
        "neutral_actions": strategy.get("neutral_actions", []),
        "action_prioritizations": strategy.get("action_prioritizations", {}),
        "reason": strategy.get("reason", ""),
        "evidence_hierarchy": strategy.get("evidence_hierarchy", {})
    }


# ==============================================================================
# DEFAULT REGISTRY BUILDER
# ==============================================================================

def create_default_tool_registry() -> ToolRegistry:
    """Build and return the standard ToolRegistry populated with all core tools."""
    registry = ToolRegistry()

    # 1. get_keyword_rankings
    registry.register(AgentToolDefinition(
        name="get_keyword_rankings",
        description="Retrieve tracked keywords and their latest search ranking positions for the current project.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Optional filter for keyword query phrase."},
                "search_engine": {"type": "string", "description": "Optional search engine filter (e.g. 'google')."},
                "country": {"type": "string", "description": "Optional country code filter (e.g. 'ET')."},
                "limit": {"type": "integer", "description": "Maximum rankings to return (default 20, max 100)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_keyword_rankings
    ))

    # 2. get_search_console_analytics
    registry.register(AgentToolDefinition(
        name="get_search_console_analytics",
        description="Retrieve cached/stored Google Search Console performance queries, impressions, clicks, CTR, and positions for the current project.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional search query filter."},
                "min_impressions": {"type": "integer", "description": "Minimum search impressions threshold."},
                "max_ctr_percent": {"type": "number", "description": "Maximum CTR percentage filter for discovering CTR optimization opportunities."},
                "limit": {"type": "integer", "description": "Maximum queries to return (default 20, max 100)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_search_console_analytics
    ))

    # 3. trigger_site_audit
    registry.register(AgentToolDefinition(
        name="trigger_site_audit",
        description="Trigger an asynchronous website crawl and technical SEO audit for the current project.",
        category=ToolCategory.SAFE_INTERNAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "start_url": {"type": "string", "description": "Optional crawl starting URL (must match project website domain)."},
                "max_pages": {"type": "integer", "description": "Maximum pages to crawl (1-200, default 50)."},
                "max_depth": {"type": "integer", "description": "Maximum crawl depth from start URL (0-10, default 3)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=True,
        handler=handle_trigger_site_audit
    ))

    # 4. get_site_audit_summary
    registry.register(AgentToolDefinition(
        name="get_site_audit_summary",
        description="Retrieve a compact summary of the latest (or specified) technical SEO site audit, including health score and aggregated issue breakdown.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "audit_id": {"type": "integer", "description": "Optional specific SiteAudit ID to retrieve."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_site_audit_summary
    ))

    # 5. get_audit_issues
    registry.register(AgentToolDefinition(
        name="get_audit_issues",
        description="Retrieve site audit technical SEO issues, warnings, and crawl diagnostics for the current project with optional filtering.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "audit_id": {"type": "integer", "description": "Optional specific SiteAudit ID filter."},
                "severity": {"type": "string", "enum": ["critical", "warning", "notice", "info"], "description": "Severity filter."},
                "issue_type": {"type": "string", "description": "Specific issue type identifier or rule code (e.g. 'missing_title', 'missing_h1')."},
                "page_url": {"type": "string", "description": "Optional page URL filter."},
                "limit": {"type": "integer", "description": "Maximum issues to return (default 20, max 100)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_audit_issues
    ))

    # 4. gsc_search_analytics (Live GSC API Query)
    registry.register(AgentToolDefinition(
        name="gsc_search_analytics",
        description="Query live Google Search Console performance metrics (clicks, impressions, CTR, average position) across custom dimensions (query, page, date, device, country) for a given date range.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format (required)."},
                "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format (required)."},
                "dimensions": {
                    "type": "array",
                    "description": "Dimensions to group by (e.g. ['query', 'page', 'country', 'device', 'date']). Defaults to ['query']."
                },
                "row_limit": {"type": "integer", "description": "Maximum rows to return (default 25, max 250)."},
                "query_filter": {"type": "string", "description": "Optional substring filter for search query."},
                "page_filter": {"type": "string", "description": "Optional substring filter for landing page URL."},
                "site_url": {"type": "string", "description": "Optional custom Search Console property URL override."}
            },
            "required": ["start_date", "end_date"]
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_gsc_search_analytics
    ))

    # 5. gsc_top_queries (Live GSC Top Queries)
    registry.register(AgentToolDefinition(
        name="gsc_top_queries",
        description="Retrieve the highest performing organic search queries by impressions and clicks from Google Search Console for a specific date range.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format (required)."},
                "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format (required)."},
                "limit": {"type": "integer", "description": "Maximum queries to return (default 20, max 100)."},
                "page_filter": {"type": "string", "description": "Optional filter for a specific landing page URL."}
            },
            "required": ["start_date", "end_date"]
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_gsc_top_queries
    ))

    # 6. gsc_top_pages (Live GSC Top Pages)
    registry.register(AgentToolDefinition(
        name="gsc_top_pages",
        description="Retrieve the highest-traffic landing pages from Google Search Console by clicks and impressions for a specific date range.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format (required)."},
                "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format (required)."},
                "limit": {"type": "integer", "description": "Maximum pages to return (default 20, max 100)."},
                "query_filter": {"type": "string", "description": "Optional filter for a specific search query phrase."}
            },
            "required": ["start_date", "end_date"]
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_gsc_top_pages
    ))

    # 7. gsc_opportunity_audit (GSC Intelligence Analyzer)
    registry.register(AgentToolDefinition(
        name="gsc_opportunity_audit",
        description="Analyze Search Console performance metrics using intelligence heuristics to discover Page 2 keyword opportunities, low-CTR SERP snippets, keyword cannibalization, and emerging search queries.",
        category=ToolCategory.SAFE_INTERNAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "min_impressions": {"type": "integer", "description": "Minimum impressions threshold for opportunity evaluation (default 10)."},
                "sync_to_insights": {"type": "boolean", "description": "Whether to sync detected opportunities into persistent SEOInsight records (default true)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=True,
        handler=handle_gsc_opportunity_audit
    ))

    # 8. gsc_performance_comparison (GSC Trend & Period Comparison)
    registry.register(AgentToolDefinition(
        name="gsc_performance_comparison",
        description="Compare Search Console performance between two date ranges (base period vs comparison period) to calculate traffic deltas, top gainers, top decliners, and search momentum trends.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "base_start_date": {"type": "string", "description": "Start date of recent/base period in YYYY-MM-DD format (required)."},
                "base_end_date": {"type": "string", "description": "End date of recent/base period in YYYY-MM-DD format (required)."},
                "comp_start_date": {"type": "string", "description": "Start date of comparison/prior period in YYYY-MM-DD format (required)."},
                "comp_end_date": {"type": "string", "description": "End date of comparison/prior period in YYYY-MM-DD format (required)."},
                "row_limit": {"type": "integer", "description": "Maximum queries to evaluate for delta comparison (default 50, max 250)."}
            },
            "required": ["base_start_date", "base_end_date", "comp_start_date", "comp_end_date"]
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_gsc_performance_comparison
    ))

    # 9. analyze_seo_opportunities (GSC + Audit Cross-Source Intelligence Correlation)
    registry.register(AgentToolDefinition(
        name="analyze_seo_opportunities",
        description="Correlate Google Search Console performance metrics with live website audit diagnostics to discover high-leverage SEO opportunities (low CTR with on-page defects, ranking decay with technical crawl blockers, high-value page vulnerabilities, and query-to-page optimizations).",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "min_impressions": {"type": "integer", "description": "Minimum impressions threshold for opportunity evaluation (default 20)."},
                "limit": {"type": "integer", "description": "Maximum prioritized opportunities to return (default 10, max 50)."},
                "page_filter": {"type": "string", "description": "Optional substring filter for landing page URL."},
                "audit_id": {"type": "integer", "description": "Optional specific SiteAudit ID to evaluate."},
                "sync_to_insights": {"type": "boolean", "description": "Whether to sync detected opportunities into persistent SEOInsight records (default false)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_analyze_seo_opportunities
    ))

    # 10. investigate_seo_opportunity (Autonomous Deep Investigation & Root Cause Engine)
    registry.register(AgentToolDefinition(
        name="investigate_seo_opportunity",
        description="Autonomously investigate a specific SEO opportunity by gathering multi-source evidence from Google Search Console and Site Audit diagnostics, classifying root cause, evaluating confidence, and generating structured recommended actions.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "opportunity_type": {
                    "type": "string",
                    "description": "Type identifier of the SEO opportunity to investigate (e.g. 'LOW_CTR_HIGH_IMPRESSIONS', 'RANKING_TECHNICAL_DECAY', 'HIGH_VALUE_PAGE_MAINTENANCE', 'QUERY_PAGE_OPPORTUNITY')."
                },
                "target_url": {
                    "type": "string",
                    "description": "Optional specific landing page URL to investigate."
                },
                "target_query": {
                    "type": "string",
                    "description": "Optional specific search query phrase associated with the opportunity."
                },
                "audit_id": {
                    "type": "integer",
                    "description": "Optional specific SiteAudit ID to evaluate."
                },
                "date_range_days": {
                    "type": "integer",
                    "description": "Number of days of Search Console metrics to analyze (default 28)."
                }
            },
            "required": ["opportunity_type"]
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_investigate_seo_opportunity
    ))

    # 11. run_intelligence_analysis
    registry.register(AgentToolDefinition(
        name="run_intelligence_analysis",
        description="Run the deterministic SEO intelligence heuristic engine to analyze ranking movements, CTR anomalies, and audit issues, generating updated SEOInsight records.",
        category=ToolCategory.SAFE_INTERNAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "trigger_reason": {"type": "string", "description": "Optional context note explaining why analysis was triggered."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=True,
        handler=handle_run_intelligence_analysis
    ))

    # 10. generate_recommendation
    registry.register(AgentToolDefinition(
        name="generate_recommendation",
        description="Generate an AI-powered, grounded SEO recommendation with strategy, checklist, and impact prediction based on an SEO insight.",
        category=ToolCategory.SAFE_INTERNAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "insight_id": {"type": "integer", "description": "ID of the SEOInsight belonging to this project."}
            },
            "required": ["insight_id"]
        },
        requires_approval=False,
        is_mutating=True,
        handler=handle_generate_recommendation
    ))

    # 11. generate_content_brief
    registry.register(AgentToolDefinition(
        name="generate_content_brief",
        description="Generate a comprehensive SEO content brief (outline, secondary keywords, search intent, FAQ, link suggestions) based on an approved recommendation.",
        category=ToolCategory.SAFE_INTERNAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "recommendation_id": {"type": "integer", "description": "ID of the SEORecommendation belonging to this project."},
                "content_type": {
                    "type": "string",
                    "enum": ["blog_post", "landing_page", "page_optimization", "technical_implementation"],
                    "description": "Optional archetype override."
                }
            },
            "required": ["recommendation_id"]
        },
        requires_approval=False,
        is_mutating=True,
        handler=handle_generate_content_brief
    ))

    # 12. generate_content_draft
    registry.register(AgentToolDefinition(
        name="generate_content_draft",
        description="Generate a full-length, publish-ready SEO content draft in Markdown with schema markup and keyword density mapping based on a content brief.",
        category=ToolCategory.SAFE_INTERNAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "content_brief_id": {"type": "integer", "description": "ID of the SEOContentBrief belonging to this project."},
                "regenerate": {"type": "boolean", "description": "Whether to regenerate and update existing draft."}
            },
            "required": ["content_brief_id"]
        },
        requires_approval=False,
        is_mutating=True,
        handler=handle_generate_content_draft
    ))

    # 13. propose_seo_action
    registry.register(AgentToolDefinition(
        name="propose_seo_action",
        description="Create a formal, structured SEOAction task proposal for human review and approval from an SEO investigation, recommendation, draft, or brief. Does NOT execute the action.",
        category=ToolCategory.HIGH_IMPACT,
        parameters_schema={
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "enum": ["investigation", "recommendation", "draft", "brief"],
                    "description": "Originating entity type."
                },
                "source_id": {"type": "integer", "description": "ID of the source entity belonging to this project (recommendation, draft, or brief)."},
                "opportunity_type": {"type": "string", "description": "Opportunity classification if proposing directly from an investigation."},
                "investigation_id": {"type": "string", "description": "Optional reference ID of an SEO investigation."},
                "target_url": {"type": "string", "description": "Target landing page URL."},
                "target_query": {"type": "string", "description": "Target search query."},
                "action_type_override": {"type": "string", "description": "Optional SEO action type override."}
            },
            "required": []
        },
        requires_approval=True,
        is_mutating=True,
        handler=handle_propose_seo_action
    ))

    # 14. get_pending_actions
    registry.register(AgentToolDefinition(
        name="get_pending_actions",
        description="Retrieve all proposed and pending SEO actions requiring human review and approval for this project.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of pending actions to return (default 20)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_pending_actions
    ))

    # 15. get_action
    registry.register(AgentToolDefinition(
        name="get_action",
        description="Retrieve full details, rationale, evidence snapshot, and approval state of a specific SEO action by ID.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "action_id": {"type": "integer", "description": "ID of the SEO action to retrieve."}
            },
            "required": ["action_id"]
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_action
    ))

    # 16. preview_action
    registry.register(AgentToolDefinition(
        name="preview_action",
        description="Generate a safe, non-destructive before/after visual diff preview for an SEOAction without modifying any live state.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "action_id": {"type": "integer", "description": "ID of the SEO action to preview."}
            },
            "required": ["action_id"]
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_preview_action
    ))

    # 17. plan_seo_actions
    registry.register(AgentToolDefinition(
        name="plan_seo_actions",
        description="Synthesize project SEO audit issues, GSC performance anomalies, and investigation findings into a cohesive, structured SEOActionPlan with deterministic risk classification, deduplication, and verification plans. Does NOT execute mutations.",
        category=ToolCategory.SAFE_INTERNAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Optional custom title for the action plan."},
                "summary": {"type": "string", "description": "Optional summary or theme for the plan."},
                "audit_id": {"type": "integer", "description": "Optional specific SiteAudit ID to prioritize."},
                "max_actions": {"type": "integer", "description": "Maximum atomic actions to include in the plan (default 10)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=True,
        handler=handle_plan_seo_actions
    ))

    # 18. get_action_plan
    registry.register(AgentToolDefinition(
        name="get_action_plan",
        description="Retrieve full details, child actions, aggregate risk level, approval status, and verification results of an SEOActionPlan by ID.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer", "description": "ID of the SEOActionPlan to retrieve."}
            },
            "required": ["plan_id"]
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_action_plan
    ))

    # 19. verify_seo_action
    registry.register(AgentToolDefinition(
        name="verify_seo_action",
        description="Perform empirical real-world verification of an executed SEOAction by inspecting live website HTML, metadata, and HTTP status codes.",
        category=ToolCategory.SAFE_INTERNAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "action_id": {"type": "integer", "description": "ID of the executed SEOAction to verify."}
            },
            "required": ["action_id"]
        },
        requires_approval=False,
        is_mutating=True,
        handler=handle_verify_seo_action
    ))

    # 20. verify_action_plan
    registry.register(AgentToolDefinition(
        name="verify_action_plan",
        description="Perform aggregate real-world verification for all executed actions within an SEOActionPlan.",
        category=ToolCategory.SAFE_INTERNAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer", "description": "ID of the SEOActionPlan to verify."}
            },
            "required": ["plan_id"]
        },
        requires_approval=False,
        is_mutating=True,
        handler=handle_verify_action_plan
    ))

    # 21. get_action_outcomes
    registry.register(AgentToolDefinition(
        name="get_action_outcomes",
        description="Retrieve aggregated historical SEO action outcomes, empirical improvement rates, and before/after search performance evidence for this project to ground future action recommendations in observed historical results.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "description": "Optional filter by action type (e.g. 'optimize_title', 'update_meta_description', 'fix_missing_h1')."},
                "target_url": {"type": "string", "description": "Optional filter by landing page URL."},
                "outcome": {
                    "type": "string",
                    "enum": ["improved", "no_change", "declined", "insufficient_data", "unknown"],
                    "description": "Optional filter by outcome classification."
                },
                "limit": {"type": "integer", "description": "Maximum recent historical sample outcomes to include (default 20, max 50)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_action_outcomes
    ))

    # 22. get_adaptive_seo_strategy
    registry.register(AgentToolDefinition(
        name="get_adaptive_seo_strategy",
        description="Retrieve calibrated adaptive SEO strategy, historical action effectiveness, and empirical planning signals for this project. Use before planning or prioritizing actions to ground recommendations in past observed outcomes.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "description": "Optional filter for specific action type (e.g. 'optimize_title', 'update_meta_description')."
                }
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_adaptive_seo_strategy
    ))

    return registry


# Module singleton
default_tool_registry = create_default_tool_registry()

def get_tool_registry() -> ToolRegistry:
    """Return the default global ToolRegistry instance."""
    return default_tool_registry
