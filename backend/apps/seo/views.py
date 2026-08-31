from django.db import transaction
from django.db.models import Sum, Avg, Count, F
from django.http import HttpResponse
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Keyword, KeywordRanking, SiteAudit, AuditIssue,
    SearchConsoleConnection, SearchAnalyticsData,
    SEOInsight, InsightSeverity, InsightStatus, InsightSource, InsightType,
    SEORecommendation, RecommendationType, RecommendationPriority, RecommendationStatus,
    SEOContentBrief, BriefContentType, BriefSearchIntent, BriefStatus,
    SEOContentDraft, DraftStatus,
    SEOAction, ActionType, ActionStatus, ActionPriority,
    AgentRun, AgentStep, AgentToolCall, AgentRunStatus, AgentActionType, AgentStepStatus
)
from .serializers import (
    KeywordSerializer, KeywordRankingSerializer,
    SiteAuditSerializer, AuditIssueSerializer,
    SearchConsoleConnectionSerializer, SearchAnalyticsDataSerializer,
    SearchConsoleSyncRequestSerializer,
    SEOInsightSerializer, SEOInsightAnalyzeRequestSerializer, SEOInsightStatusUpdateSerializer,
    SEORecommendationSerializer, SEORecommendationGenerateRequestSerializer,
    SEOContentBriefSerializer, SEOContentBriefGenerateRequestSerializer, SEOContentBriefStatusUpdateSerializer,
    SEOContentDraftSerializer, SEOContentDraftGenerateRequestSerializer, SEOContentDraftUpdateSerializer,
    SEOActionSerializer, SEOActionUpdateSerializer, SEOActionGenerateRequestSerializer,
    AgentRunSerializer, AgentRunCreateSerializer, AgentRunResumeSerializer,
    GoogleOAuthAuthorizationUrlResponseSerializer, GoogleOAuthCallbackRequestSerializer
)
from .services.search_console import GoogleSearchConsoleService
from .services.google_oauth import (
    GoogleOAuthService,
    OAuthStateService,
    InvalidOAuthStateError,
    GoogleOAuthExchangeError
)
from .services.seo_intelligence import SEOIntelligenceService
from .services.ai_seo_agent import AISeoAgentService
from .services.content_brief_service import SEOContentBriefService
from .services.content_writer_service import SEOContentWriterService
from .services.export_service import ContentBriefExportService, ContentDraftExportService
from .services.action_service import SEOActionService
from .services.action_executors import get_action_executor
from .services.agent_orchestrator import AgentOrchestrator
from apps.projects.models import Project



class KeywordViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Keyword CRUD operations.
    
    Security & Ownership:
    1. Requires authentication on all actions.
    2. Queryset is strictly filtered by `project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports optional `project_id` filtering without bypassing ownership isolation.
    """
    serializer_class = KeywordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return only keywords belonging to projects owned by the authenticated user.
        """
        queryset = Keyword.objects.filter(project__owner=self.request.user)

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset


class KeywordRankingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for KeywordRanking operations.
    
    Security & Ownership:
    1. Requires authentication on all actions.
    2. Queryset is strictly filtered by `keyword__project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports optional `keyword_id` filtering without bypassing ownership isolation.
    """
    serializer_class = KeywordRankingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return only rankings belonging to keywords owned by the authenticated user.
        """
        queryset = KeywordRanking.objects.filter(keyword__project__owner=self.request.user)

        keyword_id = self.request.query_params.get('keyword_id')
        if keyword_id:
            queryset = queryset.filter(keyword_id=keyword_id)

        return queryset


class SiteAuditViewSet(viewsets.ModelViewSet):
    """
    ViewSet for SiteAudit CRUD operations.
    
    Security & Ownership:
    1. Requires authentication on all actions.
    2. Queryset is strictly filtered by `project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports optional `project_id` filtering without bypassing ownership isolation.
    """
    serializer_class = SiteAuditSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return only site audits belonging to projects owned by the authenticated user.
        """
        queryset = SiteAudit.objects.filter(project__owner=self.request.user)

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset


class AuditIssueViewSet(viewsets.ModelViewSet):
    """
    ViewSet for AuditIssue operations.
    
    Security & Ownership:
    1. Requires authentication on all actions.
    2. Queryset is strictly filtered by `audit__project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports optional `audit_id` filtering without bypassing ownership isolation.
    """
    serializer_class = AuditIssueSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return only issues belonging to audits owned by the authenticated user.
        """
        queryset = AuditIssue.objects.filter(audit__project__owner=self.request.user)

        audit_id = self.request.query_params.get('audit_id')
        if audit_id:
            queryset = queryset.filter(audit_id=audit_id)

        return queryset


class SearchConsoleConnectionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for SearchConsoleConnection operations.
    
    Security & Ownership:
    1. Requires authentication on all actions.
    2. Queryset is strictly filtered by `project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports optional `project_id` filtering without bypassing ownership isolation.
    """
    serializer_class = SearchConsoleConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return only Search Console connections belonging to projects owned by the authenticated user.
        """
        queryset = SearchConsoleConnection.objects.filter(project__owner=self.request.user)

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset

    @action(detail=False, methods=['post'], url_path='sync')
    def sync_by_project_or_connection(self, request):
        """
        Synchronize Search Console data for a user project or connection.
        (POST /api/seo/search-console/sync/)
        """
        serializer = SearchConsoleSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        project_id = data.get('project_id')
        connection_id = data.get('connection_id')

        connection = None
        if connection_id:
            connection = SearchConsoleConnection.objects.filter(
                id=connection_id,
                project__owner=request.user
            ).first()
            if not connection:
                return Response(
                    {"detail": "Search Console connection not found or you do not have permission to access it."},
                    status=status.HTTP_404_NOT_FOUND
                )
        elif project_id:
            connection = SearchConsoleConnection.objects.filter(
                project_id=project_id,
                project__owner=request.user
            ).first()
            if not connection:
                return Response(
                    {"detail": f"No Search Console connection found for project #{project_id}."},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(
                {"detail": "Either project_id or connection_id must be provided."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not connection.is_connected:
            return Response(
                {"detail": "This Search Console connection is disconnected. Please connect the property first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            summary = GoogleSearchConsoleService.sync_search_analytics(
                connection=connection,
                start_date=data.get('start_date'),
                end_date=data.get('end_date')
            )
            return Response(summary, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response(
                {"detail": f"Synchronization failed: {str(exc)}", "sync_status": "failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='sync')
    def sync_single_connection(self, request, pk=None):
        """
        Synchronize Search Console data for a specific connection record.
        (POST /api/seo/search-console/<id>/sync/)
        """
        connection = self.get_object()  # Enforces ownership via get_queryset
        if not connection.is_connected:
            return Response(
                {"detail": "This Search Console connection is disconnected."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = SearchConsoleSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            summary = GoogleSearchConsoleService.sync_search_analytics(
                connection=connection,
                start_date=data.get('start_date'),
                end_date=data.get('end_date')
            )
            return Response(summary, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response(
                {"detail": f"Synchronization failed: {str(exc)}", "sync_status": "failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='performance')
    def performance_overview(self, request):
        """
        Retrieve high-level overview performance metrics and timeseries.
        (GET /api/seo/search-console/performance/)
        """
        return self._get_analytics_viewset().performance(request)

    @action(detail=False, methods=['get'], url_path='queries')
    def queries_breakdown(self, request):
        """
        Retrieve search query performance breakdown.
        (GET /api/seo/search-console/queries/)
        """
        return self._get_analytics_viewset().queries(request)

    @action(detail=False, methods=['get'], url_path='pages')
    def pages_breakdown(self, request):
        """
        Retrieve landing page performance breakdown.
        (GET /api/seo/search-console/pages/)
        """
        return self._get_analytics_viewset().pages(request)

    @action(detail=False, methods=['get'], url_path='devices')
    def devices_breakdown(self, request):
        """
        Retrieve device category performance breakdown.
        (GET /api/seo/search-console/devices/)
        """
        return self._get_analytics_viewset().devices(request)

    @action(detail=False, methods=['get'], url_path='countries')
    def countries_breakdown(self, request):
        """
        Retrieve country performance breakdown.
        (GET /api/seo/search-console/countries/)
        """
        return self._get_analytics_viewset().countries(request)

    def _get_analytics_viewset(self):
        analytics_viewset = SearchAnalyticsViewSet()
        analytics_viewset.request = self.request
        analytics_viewset.format_kwarg = self.format_kwarg
        return analytics_viewset


class SearchAnalyticsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for SearchAnalyticsData operations.
    
    Security & Ownership:
    1. Requires authentication on all actions.
    2. Queryset is strictly filtered by `connection__project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports ownership-safe filtering by project_id, connection_id, date, start_date,
       end_date, query, page, country, device, and search_appearance.
    """
    serializer_class = SearchAnalyticsDataSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return only Search Analytics records belonging to connections owned by the authenticated user.
        """
        queryset = SearchAnalyticsData.objects.filter(
            connection__project__owner=self.request.user
        )

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(connection__project_id=project_id)

        connection_id = self.request.query_params.get('connection_id')
        if connection_id:
            queryset = queryset.filter(connection_id=connection_id)

        date_val = self.request.query_params.get('date')
        if date_val:
            queryset = queryset.filter(date=date_val)

        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(date__gte=start_date)

        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        query_param = self.request.query_params.get('query')
        if query_param:
            queryset = queryset.filter(query__icontains=query_param)

        page_param = self.request.query_params.get('page')
        if page_param:
            queryset = queryset.filter(page__icontains=page_param)

        country = self.request.query_params.get('country')
        if country:
            queryset = queryset.filter(country__iexact=country)

        device = self.request.query_params.get('device')
        if device:
            queryset = queryset.filter(device__iexact=device)

        search_appearance = self.request.query_params.get('search_appearance')
        if search_appearance:
            queryset = queryset.filter(search_appearance__iexact=search_appearance)

        return queryset

    @action(detail=False, methods=['get'], url_path='performance')
    def performance(self, request):
        """
        Get aggregated performance summary (totals and daily timeseries).
        """
        qs = self.get_queryset()

        aggregates = qs.aggregate(
            total_clicks=Sum('clicks'),
            total_impressions=Sum('impressions'),
            avg_ctr=Avg('ctr'),
            avg_position=Avg('position')
        )

        total_clicks = aggregates['total_clicks'] or 0
        total_impressions = aggregates['total_impressions'] or 0
        average_ctr = round(float(aggregates['avg_ctr'] or 0), 4)
        if total_impressions > 0 and average_ctr == 0:
            average_ctr = round(total_clicks / total_impressions, 4)

        average_position = round(float(aggregates['avg_position'] or 0), 2)

        # Daily time series
        timeseries_qs = qs.values('date').annotate(
            clicks=Sum('clicks'),
            impressions=Sum('impressions'),
            avg_position=Avg('position')
        ).order_by('date')

        timeseries = [
            {
                "date": str(item['date']),
                "clicks": item['clicks'] or 0,
                "impressions": item['impressions'] or 0,
                "ctr": round((item['clicks'] or 0) / (item['impressions'] or 1), 4) if item['impressions'] else 0.0,
                "position": round(float(item['avg_position'] or 0), 2)
            }
            for item in timeseries_qs
        ]

        return Response({
            "total_clicks": total_clicks,
            "total_impressions": total_impressions,
            "average_ctr": average_ctr,
            "average_position": average_position,
            "timeseries": timeseries,
            "count": len(timeseries)
        })

    @action(detail=False, methods=['get'], url_path='queries')
    def queries(self, request):
        """
        Get queries performance breakdown.
        """
        qs = self.get_queryset().exclude(query='')
        results = qs.values('query').annotate(
            clicks=Sum('clicks'),
            impressions=Sum('impressions'),
            avg_position=Avg('position')
        ).order_by('-clicks', '-impressions')[:100]

        data = [
            {
                "query": item['query'],
                "clicks": item['clicks'] or 0,
                "impressions": item['impressions'] or 0,
                "ctr": round((item['clicks'] or 0) / (item['impressions'] or 1), 4) if item['impressions'] else 0.0,
                "position": round(float(item['avg_position'] or 0), 2)
            }
            for item in results
        ]
        return Response(data)

    @action(detail=False, methods=['get'], url_path='pages')
    def pages(self, request):
        """
        Get landing pages performance breakdown.
        """
        qs = self.get_queryset().exclude(page='')
        results = qs.values('page').annotate(
            clicks=Sum('clicks'),
            impressions=Sum('impressions'),
            avg_position=Avg('position')
        ).order_by('-clicks', '-impressions')[:100]

        data = [
            {
                "page": item['page'],
                "clicks": item['clicks'] or 0,
                "impressions": item['impressions'] or 0,
                "ctr": round((item['clicks'] or 0) / (item['impressions'] or 1), 4) if item['impressions'] else 0.0,
                "position": round(float(item['avg_position'] or 0), 2)
            }
            for item in results
        ]
        return Response(data)

    @action(detail=False, methods=['get'], url_path='devices')
    def devices(self, request):
        """
        Get device category performance breakdown.
        """
        qs = self.get_queryset().exclude(device='')
        results = qs.values('device').annotate(
            clicks=Sum('clicks'),
            impressions=Sum('impressions'),
            avg_position=Avg('position')
        ).order_by('-clicks')

        data = [
            {
                "device": item['device'],
                "clicks": item['clicks'] or 0,
                "impressions": item['impressions'] or 0,
                "ctr": round((item['clicks'] or 0) / (item['impressions'] or 1), 4) if item['impressions'] else 0.0,
                "position": round(float(item['avg_position'] or 0), 2)
            }
            for item in results
        ]
        return Response(data)

    @action(detail=False, methods=['get'], url_path='countries')
    def countries(self, request):
        """
        Get country performance breakdown.
        """
        qs = self.get_queryset().exclude(country='')
        results = qs.values('country').annotate(
            clicks=Sum('clicks'),
            impressions=Sum('impressions'),
            avg_position=Avg('position')
        ).order_by('-clicks')

        data = [
            {
                "country": item['country'],
                "clicks": item['clicks'] or 0,
                "impressions": item['impressions'] or 0,
                "ctr": round((item['clicks'] or 0) / (item['impressions'] or 1), 4) if item['impressions'] else 0.0,
                "position": round(float(item['avg_position'] or 0), 2)
            }
            for item in results
        ]
        return Response(data)


class SEOInsightViewSet(viewsets.ModelViewSet):
    """
    ViewSet for SEO Insights operations.
    
    Security & Ownership:
    1. Requires authentication on all actions.
    2. Queryset is strictly filtered by `project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports filtering by project_id, severity, status, insight_type, source.
    """
    serializer_class = SEOInsightSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return only SEO insights belonging to projects owned by the authenticated user.
        """
        queryset = SEOInsight.objects.filter(
            project__owner=self.request.user
        ).select_related('project', 'related_keyword')

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        insight_type = self.request.query_params.get('insight_type')
        if insight_type:
            queryset = queryset.filter(insight_type=insight_type)

        source = self.request.query_params.get('source')
        if source:
            queryset = queryset.filter(source=source)

        return queryset.order_by('-detected_at')

    @action(detail=False, methods=['post'], url_path='analyze')
    def analyze(self, request):
        """
        Execute deterministic SEO intelligence rules for the specified project.
        Returns summary of created, updated, and total open insights.
        """
        serializer = SEOInsightAnalyzeRequestSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        project_id = serializer.validated_data['project_id']

        try:
            project = Project.objects.get(id=project_id, owner=request.user)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found or not owned by authenticated user."},
                status=status.HTTP_404_NOT_FOUND
            )

        service = SEOIntelligenceService(project=project)
        result = service.analyze()
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        Get aggregated counts for project insights by severity and status.
        """
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response(
                {"detail": "project_id query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            project = Project.objects.get(id=project_id, owner=request.user)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        base_qs = SEOInsight.objects.filter(project=project)
        counts = {
            'critical': base_qs.filter(severity=InsightSeverity.CRITICAL, status=InsightStatus.OPEN).count(),
            'warning': base_qs.filter(severity=InsightSeverity.WARNING, status=InsightStatus.OPEN).count(),
            'opportunity': base_qs.filter(severity=InsightSeverity.OPPORTUNITY, status=InsightStatus.OPEN).count(),
            'info': base_qs.filter(severity=InsightSeverity.INFO, status=InsightStatus.OPEN).count(),
            'open_total': base_qs.filter(status=InsightStatus.OPEN).count(),
            'resolved_total': base_qs.filter(status=InsightStatus.RESOLVED).count(),
            'dismissed_total': base_qs.filter(status=InsightStatus.DISMISSED).count(),
            'total': base_qs.count()
        }
        return Response(counts, status=status.HTTP_200_OK)


class SEORecommendationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for AI-generated SEO Recommendations.
    
    Security & Ownership:
    1. Requires authentication on all endpoints.
    2. Queryset strictly isolated by `project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports filtering by project_id, insight_id, status, priority, recommendation_type.
    """
    serializer_class = SEORecommendationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return only recommendations belonging to projects owned by the authenticated user.
        """
        queryset = SEORecommendation.objects.filter(
            project__owner=self.request.user
        ).select_related('project', 'insight')

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        insight_id = self.request.query_params.get('insight_id')
        if insight_id:
            queryset = queryset.filter(insight_id=insight_id)

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        rec_type = self.request.query_params.get('recommendation_type')
        if rec_type:
            queryset = queryset.filter(recommendation_type=rec_type)

        return queryset.order_by('-created_at')

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """
        Trigger AI recommendation generation for specified insights or all open insights of a project.
        """
        serializer = SEORecommendationGenerateRequestSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        project_id = serializer.validated_data['project_id']
        insight_ids = serializer.validated_data.get('insight_ids', [])

        try:
            project = Project.objects.get(id=project_id, owner=request.user)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found or not owned by authenticated user."},
                status=status.HTTP_404_NOT_FOUND
            )

        agent = AISeoAgentService(project=project)
        recs = agent.generate_batch(insight_ids=insight_ids if insight_ids else None)
        out_serializer = SEORecommendationSerializer(recs, many=True)
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        Get aggregated counts for project recommendations by priority and status.
        """
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response(
                {"detail": "project_id query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            project = Project.objects.get(id=project_id, owner=request.user)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        base_qs = SEORecommendation.objects.filter(project=project)
        counts = {
            'critical': base_qs.filter(priority=RecommendationPriority.CRITICAL, status=RecommendationStatus.PENDING_REVIEW).count(),
            'high': base_qs.filter(priority=RecommendationPriority.HIGH, status=RecommendationStatus.PENDING_REVIEW).count(),
            'medium': base_qs.filter(priority=RecommendationPriority.MEDIUM, status=RecommendationStatus.PENDING_REVIEW).count(),
            'low': base_qs.filter(priority=RecommendationPriority.LOW, status=RecommendationStatus.PENDING_REVIEW).count(),
            'pending_review': base_qs.filter(status=RecommendationStatus.PENDING_REVIEW).count(),
            'reviewed': base_qs.filter(status=RecommendationStatus.REVIEWED).count(),
            'applied': base_qs.filter(status=RecommendationStatus.APPLIED).count(),
            'dismissed': base_qs.filter(status=RecommendationStatus.DISMISSED).count(),
            'total': base_qs.count()
        }
        return Response(counts, status=status.HTTP_200_OK)


class SEOContentBriefViewSet(viewsets.ModelViewSet):
    """
    ViewSet for AI-generated SEO Content Briefs.
    
    Security & Ownership:
    1. Requires authentication on all endpoints.
    2. Queryset strictly isolated by `project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports filtering by project_id, recommendation_id, content_type, status.
    """
    serializer_class = SEOContentBriefSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return only content briefs belonging to projects owned by the authenticated user.
        """
        queryset = SEOContentBrief.objects.filter(
            project__owner=self.request.user
        ).select_related('project', 'recommendation')

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        recommendation_id = self.request.query_params.get('recommendation_id')
        if recommendation_id:
            queryset = queryset.filter(recommendation_id=recommendation_id)

        content_type = self.request.query_params.get('content_type')
        if content_type:
            queryset = queryset.filter(content_type=content_type)

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset.order_by('-created_at')

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """
        Trigger AI content brief synthesis for a specific recommendation.
        """
        serializer = SEOContentBriefGenerateRequestSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        project_id = serializer.validated_data['project_id']
        rec_id = serializer.validated_data['recommendation_id']
        content_type = serializer.validated_data.get('content_type')

        try:
            project = Project.objects.get(id=project_id, owner=request.user)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found or not owned by authenticated user."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            recommendation = SEORecommendation.objects.get(id=rec_id, project=project)
        except SEORecommendation.DoesNotExist:
            return Response(
                {"detail": "Recommendation not found for this project."},
                status=status.HTTP_404_NOT_FOUND
            )

        service = SEOContentBriefService(project=project)
        brief = service.generate_for_recommendation(
            recommendation=recommendation,
            content_type_override=content_type
        )
        out_serializer = SEOContentBriefSerializer(brief)
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='export')
    def export(self, request, pk=None):
        """
        Export a content brief in Markdown, CSV, or PDF format.
        (GET /api/seo/ai/content-briefs/<id>/export/?export_format=markdown|csv|pdf)
        """
        brief = self.get_object()  # Enforces project.owner == request.user
        export_format = str(
            request.query_params.get('export_format') or request.query_params.get('format') or 'markdown'
        ).lower().strip()
        slug_safe = brief.suggested_slug.strip('/').replace('/', '_') or f"brief_{brief.id}"

        if export_format == 'csv':
            csv_content = ContentBriefExportService.export_csv(brief)
            response = HttpResponse(csv_content, content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{slug_safe}_brief.csv"'
            return response

        elif export_format == 'pdf':
            pdf_bytes = ContentBriefExportService.export_pdf(brief)
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{slug_safe}_brief.pdf"'
            return response

        # Default Markdown
        markdown_content = ContentBriefExportService.export_markdown(brief)
        response = HttpResponse(markdown_content, content_type='text/markdown; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{slug_safe}_brief.md"'
        return response


class SEOContentDraftViewSet(viewsets.ModelViewSet):
    """
    ViewSet for AI-generated SEO Content Drafts.

    Security & Ownership:
    1. Requires authentication on all endpoints.
    2. Queryset strictly isolated by `project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports filtering by project_id, content_brief_id, content_type, status.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return SEOContentDraftUpdateSerializer
        return SEOContentDraftSerializer

    def get_queryset(self):
        """
        Return only content drafts belonging to projects owned by the authenticated user.
        """
        queryset = SEOContentDraft.objects.filter(
            project__owner=self.request.user
        ).select_related('project', 'brief', 'recommendation', 'insight')

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        brief_id = self.request.query_params.get('content_brief_id') or self.request.query_params.get('brief_id')
        if brief_id:
            queryset = queryset.filter(brief_id=brief_id)

        content_type = self.request.query_params.get('content_type')
        if content_type:
            queryset = queryset.filter(content_type=content_type)

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset.order_by('-created_at')

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """
        Trigger AI content draft synthesis for an approved or completed content brief.
        (POST /api/seo/ai/content-drafts/generate/)
        """
        serializer = SEOContentDraftGenerateRequestSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        project_id = serializer.validated_data['project_id']
        brief_id = serializer.validated_data['content_brief_id']
        regenerate = serializer.validated_data.get('regenerate', False)

        try:
            project = Project.objects.get(id=project_id, owner=request.user)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found or not owned by authenticated user."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            brief = SEOContentBrief.objects.get(id=brief_id, project=project)
        except SEOContentBrief.DoesNotExist:
            return Response(
                {"detail": "Content brief not found for this project."},
                status=status.HTTP_404_NOT_FOUND
            )

        draft = SEOContentWriterService.generate_for_brief(
            project=project,
            brief=brief,
            regenerate=regenerate
        )
        out_serializer = SEOContentDraftSerializer(draft)
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='export')
    def export(self, request, pk=None):
        """
        Export an SEO Content Draft in Markdown, HTML, or PDF format.
        (GET /api/seo/ai/content-drafts/<id>/export/?export_format=markdown|html|pdf)
        """
        draft = self.get_object()  # Enforces project.owner == request.user
        export_format = str(
            request.query_params.get('export_format') or request.query_params.get('format') or 'markdown'
        ).lower().strip()
        slug_safe = draft.suggested_slug.strip('/').replace('/', '_') or f"draft_{draft.id}"

        if export_format == 'html':
            html_content = ContentDraftExportService.export_html(draft)
            response = HttpResponse(html_content, content_type='text/html; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{slug_safe}_draft.html"'
            return response

        elif export_format == 'pdf':
            pdf_bytes = ContentDraftExportService.export_pdf(draft)
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{slug_safe}_draft.pdf"'
            return response

        # Default Markdown
        markdown_content = ContentDraftExportService.export_markdown(draft)
        response = HttpResponse(markdown_content, content_type='text/markdown; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{slug_safe}_draft.md"'
        return response


class SEOActionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for AI-generated and human-approved SEO Actions.

    Security & Ownership:
    1. Requires authentication on all endpoints.
    2. Queryset strictly isolated by `project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports filtering by project_id, recommendation_id, content_draft_id, content_brief_id, action_type, priority, status.
    5. Human review & approval endpoints: review, approve, reject, cancel.
    6. Safe mock execution endpoint: execute (rejects unapproved actions).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return SEOActionUpdateSerializer
        return SEOActionSerializer

    def get_queryset(self):
        """
        Return only SEO actions belonging to projects owned by the authenticated user.
        """
        queryset = SEOAction.objects.filter(
            project__owner=self.request.user
        ).select_related('project', 'recommendation', 'brief', 'draft')

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        recommendation_id = self.request.query_params.get('recommendation_id')
        if recommendation_id:
            queryset = queryset.filter(recommendation_id=recommendation_id)

        draft_id = self.request.query_params.get('content_draft_id') or self.request.query_params.get('draft_id')
        if draft_id:
            queryset = queryset.filter(draft_id=draft_id)

        brief_id = self.request.query_params.get('content_brief_id') or self.request.query_params.get('brief_id')
        if brief_id:
            queryset = queryset.filter(brief_id=brief_id)

        action_type = self.request.query_params.get('action_type')
        if action_type:
            queryset = queryset.filter(action_type=action_type)

        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset.order_by('-created_at')

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """
        Synthesize an executable SEOAction from an SEORecommendation, SEOContentDraft, or SEOContentBrief.
        (POST /api/seo/ai/actions/generate/)
        """
        serializer = SEOActionGenerateRequestSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        project_id = serializer.validated_data['project_id']
        rec_id = serializer.validated_data.get('recommendation_id')
        draft_id = serializer.validated_data.get('content_draft_id')
        brief_id = serializer.validated_data.get('content_brief_id')
        action_type_override = serializer.validated_data.get('action_type')

        try:
            project = Project.objects.get(id=project_id, owner=request.user)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found or not owned by authenticated user."},
                status=status.HTTP_404_NOT_FOUND
            )

        service = SEOActionService(project=project)

        if draft_id:
            try:
                draft = SEOContentDraft.objects.get(id=draft_id, project=project)
            except SEOContentDraft.DoesNotExist:
                return Response({"detail": "Content draft not found for this project."}, status=status.HTTP_404_NOT_FOUND)
            action = service.generate_for_draft(draft)

        elif brief_id:
            try:
                brief = SEOContentBrief.objects.get(id=brief_id, project=project)
            except SEOContentBrief.DoesNotExist:
                return Response({"detail": "Content brief not found for this project."}, status=status.HTTP_404_NOT_FOUND)
            action = service.generate_for_brief(brief)

        elif rec_id:
            try:
                rec = SEORecommendation.objects.get(id=rec_id, project=project)
            except SEORecommendation.DoesNotExist:
                return Response({"detail": "Recommendation not found for this project."}, status=status.HTTP_404_NOT_FOUND)
            action = service.generate_for_recommendation(rec, action_type_override=action_type_override)
        else:
            return Response(
                {"detail": "Must provide recommendation_id, content_draft_id, or content_brief_id."},
                status=status.HTTP_400_BAD_REQUEST
            )

        out_serializer = SEOActionSerializer(action)
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='review')
    def review(self, request, pk=None):
        """
        Transition an SEOAction to REVIEWED status.
        (POST /api/seo/ai/actions/<id>/review/)
        """
        action_obj = self.get_object()  # Enforces project.owner == request.user
        action_obj.status = ActionStatus.REVIEWED
        action_obj.save(update_fields=['status', 'updated_at'])
        serializer = SEOActionSerializer(action_obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """
        Human approves the SEOAction, making it ready to execute.
        (POST /api/seo/ai/actions/<id>/approve/)
        """
        action_obj = self.get_object()  # Enforces project.owner == request.user
        action_obj.status = ActionStatus.APPROVED
        action_obj.save(update_fields=['status', 'updated_at'])
        serializer = SEOActionSerializer(action_obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        """
        Human rejects the proposed SEOAction.
        (POST /api/seo/ai/actions/<id>/reject/)
        """
        action_obj = self.get_object()  # Enforces project.owner == request.user
        action_obj.status = ActionStatus.REJECTED
        action_obj.save(update_fields=['status', 'updated_at'])
        serializer = SEOActionSerializer(action_obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        """
        Cancel an existing SEOAction.
        (POST /api/seo/ai/actions/<id>/cancel/)
        """
        action_obj = self.get_object()  # Enforces project.owner == request.user
        action_obj.status = ActionStatus.CANCELLED
        action_obj.save(update_fields=['status', 'updated_at'])
        serializer = SEOActionSerializer(action_obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='execute')
    def execute(self, request, pk=None):
        """
        Execute an approved SEOAction through the safe execution engine.
        Guarantees that unapproved actions cannot be executed.
        (POST /api/seo/ai/actions/<id>/execute/)
        """
        action_obj = self.get_object()  # Enforces project.owner == request.user

        if action_obj.status not in [ActionStatus.APPROVED, ActionStatus.READY_TO_EXECUTE]:
            return Response(
                {
                    "detail": (
                        f"Cannot execute action #{action_obj.id}. Current status is '{action_obj.get_status_display()}'. "
                        "A human must review and approve the action before execution."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        executor = get_action_executor()
        try:
            result = executor.execute(action_obj)
            serializer = SEOActionSerializer(action_obj)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"detail": f"Execution error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='status-counts')
    def status_counts(self, request):
        """
        Return action status counts for the selected project.
        (GET /api/seo/ai/actions/status-counts/?project_id=<id>)
        """
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response({"detail": "project_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = Project.objects.get(id=project_id, owner=request.user)
        except Project.DoesNotExist:
            return Response({"detail": "Project not found or not owned by user."}, status=status.HTTP_404_NOT_FOUND)

        base_qs = SEOAction.objects.filter(project=project)
        counts = {
            'proposed': base_qs.filter(status=ActionStatus.PROPOSED).count(),
            'reviewed': base_qs.filter(status=ActionStatus.REVIEWED).count(),
            'approved': base_qs.filter(status=ActionStatus.APPROVED).count(),
            'completed': base_qs.filter(status=ActionStatus.COMPLETED).count(),
            'rejected': base_qs.filter(status=ActionStatus.REJECTED).count(),
            'cancelled': base_qs.filter(status=ActionStatus.CANCELLED).count(),
            'total': base_qs.count()
        }
        return Response(counts, status=status.HTTP_200_OK)


class AgentRunViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing autonomous AgentRun sessions.
    Provides endpoints for creating, listing, retrieving, and resuming agent runs.
    Endpoints:
    - GET /api/seo/ai/agent/runs/ (list runs for accessible projects, optional ?project=<id>)
    - POST /api/seo/ai/agent/runs/ (start a new run)
    - GET /api/seo/ai/agent/runs/{id}/ (retrieve run with steps and tool calls)
    - POST /api/seo/ai/agent/runs/{id}/resume/ (resume paused run with approved/rejected decision)
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AgentRunSerializer

    def get_queryset(self):
        qs = AgentRun.objects.filter(project__owner=self.request.user).prefetch_related('steps__tool_calls')
        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    def create(self, request, *args, **kwargs):
        create_serializer = AgentRunCreateSerializer(data=request.data, context={'request': request})
        create_serializer.is_valid(raise_exception=True)

        project = create_serializer.validated_data['project']
        goal = create_serializer.validated_data['goal']

        orchestrator = AgentOrchestrator(
            project=project,
            user=request.user
        )
        snapshot = orchestrator._capture_project_baseline()

        with transaction.atomic():
            run = AgentRun.objects.create(
                project=project,
                user=request.user,
                goal=goal,
                status=AgentRunStatus.PENDING,
                plan=[],
                context_snapshot=snapshot,
                max_steps=15,
                total_steps=0
            )

        # Enqueue background Celery task
        from apps.seo.tasks import execute_agent_run
        execute_agent_run.delay(run.id)

        # Return immediately with pending state
        run.refresh_from_db()
        response_serializer = AgentRunSerializer(run, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='resume')
    def resume(self, request, pk=None):
        run = self.get_object()

        resume_serializer = AgentRunResumeSerializer(data=request.data)
        resume_serializer.is_valid(raise_exception=True)
        decision = resume_serializer.validated_data.get('decision', 'approved')

        from apps.seo.tasks import execute_agent_run

        with transaction.atomic():
            locked_run = AgentRun.objects.select_for_update().get(id=run.id)
            if locked_run.status != AgentRunStatus.WAITING_FOR_APPROVAL:
                return Response(
                    {
                        "detail": f"Cannot resume run #{locked_run.id}. Current status is '{locked_run.get_status_display()}'. Only runs waiting for approval can be resumed."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if decision == 'rejected':
                execute_agent_run(run.id, is_resume=True, approval_decision='rejected')
            else:
                execute_agent_run.delay(run.id, is_resume=True, approval_decision='approved')

        locked_run.refresh_from_db()
        response_serializer = AgentRunSerializer(locked_run, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='events')
    def events(self, request, pk=None):
        """
        Retrieve historical/replayed AgentEvents for an AgentRun.
        Supports sequence cursor filtering: ?after_sequence=<int>.
        Guarantees strict tenant isolation, ascending sequence order, and payload sanitization.
        """
        run = self.get_object()
        after_seq_raw = request.query_params.get('after_sequence', '0')
        try:
            after_seq = int(after_seq_raw)
        except (TypeError, ValueError):
            after_seq = 0

        from .services.agent_events import get_agent_run_events
        events_data = get_agent_run_events(run, after_sequence=after_seq)
        return Response(events_data, status=status.HTTP_200_OK)


class GoogleOAuthAuthorizationUrlView(APIView):
    """
    Generate Google OAuth2 authorization URL for connecting a project to Google Search Console.

    Security & Ownership:
    1. Requires authentication.
    2. Enforces project ownership: users cannot generate authorization URLs for projects they do not own.
    3. Generates cryptographically signed, tamper-proof state bound to the authenticated user and project.
    4. Excludes client secrets and sensitive data.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response(
                {"detail": "project_id query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            project = Project.objects.get(id=project_id, owner=request.user)
        except (Project.DoesNotExist, ValueError):
            return Response(
                {"detail": f"Project #{project_id} not found or you do not have permission to access it."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            auth_url = GoogleOAuthService.get_authorization_url(project=project, user=request.user)
            serializer = GoogleOAuthAuthorizationUrlResponseSerializer(data={"authorization_url": auth_url})
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response(
                {"detail": f"Google OAuth configuration error: {str(exc)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as exc:
            return Response(
                {"detail": f"Failed to generate authorization URL: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GoogleOAuthCallbackView(APIView):
    """
    Handle OAuth2 callback from Google, exchange authorization code, verify identity,
    and establish or update the encrypted SearchConsoleConnection.

    Supports:
    - POST /api/seo/integrations/google/callback/ (with JSON body: code, state, error)
    - GET  /api/seo/integrations/google/callback/ (with query parameters: code, state, error)

    Security:
    1. Cryptographic state verification protects against CSRF, forgery, expiration, and replay.
    2. Validates user/project binding from state and enforces tenant isolation.
    3. Symmetric Fernet encryption at rest for refresh token.
    4. Plaintext tokens and client secrets are strictly sanitized and never returned in responses.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return self._handle_callback(request, data=request.query_params)

    def post(self, request):
        return self._handle_callback(request, data=request.data)

    def _handle_callback(self, request, data):
        serializer = GoogleOAuthCallbackRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        error = validated.get('error')
        if error:
            error_msg = "Google authorization was denied by the user." if error in ['access_denied', 'consent_denied'] else f"Google authorization error: {error}"
            return Response({"detail": error_msg}, status=status.HTTP_400_BAD_REQUEST)

        code = validated.get('code')
        state = validated.get('state')
        redirect_uri = validated.get('redirect_uri')

        if not code or not code.strip():
            return Response({"detail": "Authorization code is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not state or not state.strip():
            return Response({"detail": "OAuth state parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate cryptographic state token
        try:
            project, state_user = OAuthStateService.verify_state(
                raw_state=state,
                expected_user=request.user if request.user.is_authenticated else None
            )
        except InvalidOAuthStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Exchange authorization code for tokens and verified Google user identity
        try:
            tokens = GoogleOAuthService.exchange_code(code=code, redirect_uri=redirect_uri)
            user_identity = GoogleOAuthService.fetch_user_identity(
                access_token=tokens.get('access_token'),
                id_token=tokens.get('id_token')
            )
            connection = GoogleOAuthService.complete_oauth_connection(
                project=project,
                token_data=tokens,
                user_identity=user_identity
            )
            response_serializer = SearchConsoleConnectionSerializer(connection)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        except GoogleOAuthExchangeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"An unexpected error occurred during Google Search Console authorization: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
