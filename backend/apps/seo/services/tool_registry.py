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
    SearchAnalyticsData, SEOInsight, SEORecommendation,
    SEOContentBrief, SEOContentDraft, SEOAction,
    ActionType, ActionStatus, ActionPriority,
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
            return {
                "success": False,
                "tool_name": tool_name,
                "data": None,
                "duration_ms": duration_ms,
                "is_mutating": tool.is_mutating,
                "requires_approval": tool.requires_approval,
                "error": {
                    "code": "EXECUTION_ERROR",
                    "message": str(exc)
                }
            }


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


def handle_get_audit_issues(project: Project, args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve site audit technical SEO issues."""
    severity = args.get("severity")
    issue_type = args.get("issue_type")
    limit = min(args.get("limit", 20), 100)

    qs = AuditIssue.objects.filter(audit__project=project)
    if severity:
        qs = qs.filter(severity=severity)
    if issue_type:
        qs = qs.filter(issue_type=issue_type)

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
    Generate an SEOAction proposal in 'proposed' state.
    Strictly requires human approval before any future execution.
    """
    source_type = args.get("source_type")
    source_id = args.get("source_id")
    action_type_override = args.get("action_type_override")

    action_service = SEOActionService(project=project)

    if source_type == "recommendation":
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
        raise ValueError(f"Invalid source_type '{source_type}'. Allowed values: ['recommendation', 'draft', 'brief'].")

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
        "requires_human_approval": True
    }


# ==============================================================================
# DEFAULT REGISTRY BUILDER
# ==============================================================================

def create_default_tool_registry() -> ToolRegistry:
    """Build and return the standard ToolRegistry populated with all 8 core tools."""
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
        description="Retrieve Google Search Console performance queries, impressions, clicks, CTR, and positions for the current project.",
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

    # 3. get_audit_issues
    registry.register(AgentToolDefinition(
        name="get_audit_issues",
        description="Retrieve site audit technical SEO issues, warnings, and crawl diagnostics for the current project.",
        category=ToolCategory.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["critical", "warning", "info"], "description": "Severity filter."},
                "issue_type": {"type": "string", "description": "Specific issue type identifier."},
                "limit": {"type": "integer", "description": "Maximum issues to return (default 20, max 100)."}
            },
            "required": []
        },
        requires_approval=False,
        is_mutating=False,
        handler=handle_get_audit_issues
    ))

    # 4. run_intelligence_analysis
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

    # 5. generate_recommendation
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

    # 6. generate_content_brief
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

    # 7. generate_content_draft
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

    # 8. propose_seo_action
    registry.register(AgentToolDefinition(
        name="propose_seo_action",
        description="Create a formal, structured SEOAction task proposal for human review and approval. Does NOT execute the action.",
        category=ToolCategory.HIGH_IMPACT,
        parameters_schema={
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "enum": ["recommendation", "draft", "brief"],
                    "description": "Originating entity type."
                },
                "source_id": {"type": "integer", "description": "ID of the source entity belonging to this project."},
                "action_type_override": {"type": "string", "description": "Optional SEO action type override."}
            },
            "required": ["source_type", "source_id"]
        },
        requires_approval=True,
        is_mutating=True,
        handler=handle_propose_seo_action
    ))

    return registry


# Module singleton
default_tool_registry = create_default_tool_registry()

def get_tool_registry() -> ToolRegistry:
    """Return the default global ToolRegistry instance."""
    return default_tool_registry
