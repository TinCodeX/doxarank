from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    KeywordViewSet, KeywordRankingViewSet,
    SiteAuditViewSet, AuditIssueViewSet,
    SearchConsoleConnectionViewSet, SearchAnalyticsViewSet,
    SEOInsightViewSet, SEORecommendationViewSet,
    SEOContentBriefViewSet, SEOContentDraftViewSet,
    SEOActionViewSet, SEOActionPlanViewSet, AgentRunViewSet,
    GoogleOAuthAuthorizationUrlView, GoogleOAuthCallbackView,
    SEOAdaptiveStrategyView, SEOAgentOrchestrationView,
    MCPServersView, MCPToolsView, AgentEvaluationView,
    SEOCollaborationMemoryView, SEOCollaborationMemorySummaryView,
    SEOCollaborationConflictsView,
    SEOCollaborationTasksView, SEOCollaborationTasksSummaryView,
    SEOCollaborationTasksGraphView
)

app_name = 'seo'

router = DefaultRouter()
router.register('keywords', KeywordViewSet, basename='keyword')
router.register('rankings', KeywordRankingViewSet, basename='ranking')
router.register('audits', SiteAuditViewSet, basename='siteaudit')
router.register('issues', AuditIssueViewSet, basename='auditissue')
router.register('search-console', SearchConsoleConnectionViewSet, basename='search-console')
router.register('search-analytics', SearchAnalyticsViewSet, basename='search-analytics')
router.register('insights', SEOInsightViewSet, basename='seoinsight')
router.register('ai/recommendations', SEORecommendationViewSet, basename='seorecommendation')
router.register('ai/content-briefs', SEOContentBriefViewSet, basename='seocontentbrief')
router.register('ai/content-drafts', SEOContentDraftViewSet, basename='seocontentdraft')
router.register('ai/actions', SEOActionViewSet, basename='seoaction')
router.register('ai/action-plans', SEOActionPlanViewSet, basename='seoactionplan')
router.register('ai/agent/runs', AgentRunViewSet, basename='agent-run')


urlpatterns = [
    path('ai/mcp/servers/', MCPServersView.as_view(), name='seo-mcp-servers'),
    path('ai/mcp/tools/', MCPToolsView.as_view(), name='seo-mcp-tools'),
    path('ai/agent/evaluation/<int:run_id>/', AgentEvaluationView.as_view(), name='seo-agent-evaluation'),
    path('ai/orchestrate/agents/', SEOAgentOrchestrationView.as_view(), name='seo-agent-orchestrate-agents'),
    path('ai/orchestrate/', SEOAgentOrchestrationView.as_view(), name='seo-agent-orchestrate'),
    path('ai/orchestrate/<str:run_id>/memory/summary/', SEOCollaborationMemorySummaryView.as_view(), name='seo-orchestrate-memory-summary'),
    path('ai/orchestrate/<str:run_id>/memory/', SEOCollaborationMemoryView.as_view(), name='seo-orchestrate-memory'),
    path('ai/orchestrate/<str:run_id>/conflicts/', SEOCollaborationConflictsView.as_view(), name='seo-orchestrate-conflicts'),
    path('ai/orchestrate/<str:run_id>/tasks/summary/', SEOCollaborationTasksSummaryView.as_view(), name='seo-orchestrate-tasks-summary'),
    path('ai/orchestrate/<str:run_id>/tasks/graph/', SEOCollaborationTasksGraphView.as_view(), name='seo-orchestrate-tasks-graph'),
    path('ai/orchestrate/<str:run_id>/tasks/', SEOCollaborationTasksView.as_view(), name='seo-orchestrate-tasks'),
    path('ai/strategy/', SEOAdaptiveStrategyView.as_view(), name='seo-adaptive-strategy'),
    path('integrations/google/authorization-url/', GoogleOAuthAuthorizationUrlView.as_view(), name='google-oauth-authorization-url'),
    path('integrations/google/callback/', GoogleOAuthCallbackView.as_view(), name='google-oauth-callback'),
    path('', include(router.urls)),
]
