from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    KeywordViewSet, KeywordRankingViewSet,
    SiteAuditViewSet, AuditIssueViewSet,
    SearchConsoleConnectionViewSet, SearchAnalyticsViewSet,
    SEOInsightViewSet, SEORecommendationViewSet,
    SEOContentBriefViewSet, SEOContentDraftViewSet,
    SEOActionViewSet, SEOActionPlanViewSet, AgentRunViewSet,
    ContinuousOperationViewSet, SEOEventViewSet, AutonomousMonitoringViewSet,
    AutonomousRemediationViewSet, ExternalIntegrationViewSet,
    LongTermSEOStrategyViewSet, StrategicObjectiveViewSet,
    StrategicInitiativeViewSet, StrategyReviewRecordViewSet,
    GoogleOAuthAuthorizationUrlView, GoogleOAuthCallbackView,
    SEOAdaptiveStrategyView, SEOAgentOrchestrationView,
    MCPServersView, MCPToolsView, AgentEvaluationView,
    SEOCollaborationMemoryView, SEOCollaborationMemorySummaryView,
    SEOCollaborationConflictsView,
    SEOCollaborationTasksView, SEOCollaborationTasksSummaryView,
    SEOCollaborationTasksGraphView,
    SEOAgentLearningPerformanceView, SEOCollaborationLearningView,
    SEOReasoningCaseDetailView, SEOCollaborationReasoningView,
    SEOReasoningCaseDetailView, SEOCollaborationReasoningView,
    SEOCollaborationIntegrationsView,
    PlatformHealthCheckView, PlatformReadinessCheckView, PlatformLivenessCheckView,
    PlatformMetricsView, PlatformAlertsView, PlatformCircuitBreakersView,
    PlatformCircuitBreakerDetailView, PlatformOperatorActionsView,
    PlatformRunInspectionView, PlatformRunRecoveryView, PlatformAuditLogView
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
router.register('ai/operations', ContinuousOperationViewSet, basename='continuous-operation')
router.register('ai/events', SEOEventViewSet, basename='seo-ai-events')
router.register('ai/monitoring', AutonomousMonitoringViewSet, basename='ai-monitoring')
router.register('ai/remediation', AutonomousRemediationViewSet, basename='ai-remediation')
router.register('ai/integrations', ExternalIntegrationViewSet, basename='external-integrations')
router.register('ai/long-term-strategy', LongTermSEOStrategyViewSet, basename='long-term-strategy')
router.register('ai/strategic-objectives', StrategicObjectiveViewSet, basename='strategic-objective')
router.register('ai/strategic-initiatives', StrategicInitiativeViewSet, basename='strategic-initiative')
router.register('ai/strategy-reviews', StrategyReviewRecordViewSet, basename='strategy-review')


urlpatterns = [
    # Milestone 6.7: Production Agent Platform Endpoints
    path('ai/platform/health/', PlatformHealthCheckView.as_view(), name='platform-health'),
    path('ai/platform/readiness/', PlatformReadinessCheckView.as_view(), name='platform-readiness'),
    path('ai/platform/liveness/', PlatformLivenessCheckView.as_view(), name='platform-liveness'),
    path('ai/platform/metrics/', PlatformMetricsView.as_view(), name='platform-metrics'),
    path('ai/platform/alerts/', PlatformAlertsView.as_view(), name='platform-alerts'),
    path('ai/platform/circuit-breakers/', PlatformCircuitBreakersView.as_view(), name='platform-circuit-breakers'),
    path('ai/platform/circuit-breakers/<str:service_name>/', PlatformCircuitBreakerDetailView.as_view(), name='platform-circuit-breaker-detail'),
    path('ai/platform/operator/actions/', PlatformOperatorActionsView.as_view(), name='platform-operator-actions'),
    path('ai/platform/runs/<int:run_id>/inspect/', PlatformRunInspectionView.as_view(), name='platform-run-inspect'),
    path('ai/platform/runs/<int:run_id>/recover/', PlatformRunRecoveryView.as_view(), name='platform-run-recover'),
    path('ai/platform/audit-log/', PlatformAuditLogView.as_view(), name='platform-audit-log'),

    # Existing Milestone Endpoints
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
    path('ai/orchestrate/<str:run_id>/learning/', SEOCollaborationLearningView.as_view(), name='seo-orchestrate-learning'),
    path('ai/orchestrate/<str:run_id>/reasoning/', SEOCollaborationReasoningView.as_view(), name='seo-orchestrate-reasoning'),
    path('ai/orchestrate/<str:run_id>/integrations/', SEOCollaborationIntegrationsView.as_view(), name='seo-orchestrate-integrations'),
    path('ai/reasoning/<str:case_id>/', SEOReasoningCaseDetailView.as_view(), name='seo-reasoning-case-detail'),
    path('ai/learning/performance/', SEOAgentLearningPerformanceView.as_view(), name='seo-agent-learning-performance'),
    path('ai/strategy/', SEOAdaptiveStrategyView.as_view(), name='seo-adaptive-strategy'),
    path('integrations/google/authorization-url/', GoogleOAuthAuthorizationUrlView.as_view(), name='google-oauth-authorization-url'),
    path('integrations/google/callback/', GoogleOAuthCallbackView.as_view(), name='google-oauth-callback'),
    # Standalone SEO Tools
    path('tools/', include('apps.seo.tools.urls')),
    path('', include(router.urls)),
]

