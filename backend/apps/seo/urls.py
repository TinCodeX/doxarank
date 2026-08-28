from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    KeywordViewSet, KeywordRankingViewSet,
    SiteAuditViewSet, AuditIssueViewSet,
    SearchConsoleConnectionViewSet, SearchAnalyticsViewSet,
    SEOInsightViewSet, SEORecommendationViewSet,
    SEOContentBriefViewSet, SEOContentDraftViewSet,
    SEOActionViewSet, AgentRunViewSet
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
router.register('ai/agent/runs', AgentRunViewSet, basename='agent-run')


urlpatterns = [
    path('', include(router.urls)),
]


