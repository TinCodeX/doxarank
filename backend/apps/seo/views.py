from django.db.models import Sum, Avg, Count, F
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Keyword, KeywordRanking, SiteAudit, AuditIssue,
    SearchConsoleConnection, SearchAnalyticsData,
    SEOInsight, InsightSeverity, InsightStatus, InsightSource, InsightType
)
from .serializers import (
    KeywordSerializer, KeywordRankingSerializer,
    SiteAuditSerializer, AuditIssueSerializer,
    SearchConsoleConnectionSerializer, SearchAnalyticsDataSerializer,
    SearchConsoleSyncRequestSerializer,
    SEOInsightSerializer, SEOInsightAnalyzeRequestSerializer, SEOInsightStatusUpdateSerializer
)
from .services.search_console import GoogleSearchConsoleService
from .services.seo_intelligence import SEOIntelligenceService
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





