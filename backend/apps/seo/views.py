from rest_framework import viewsets, permissions
from .models import (
    Keyword, KeywordRanking, SiteAudit, AuditIssue,
    SearchConsoleConnection, SearchAnalyticsData
)
from .serializers import (
    KeywordSerializer, KeywordRankingSerializer,
    SiteAuditSerializer, AuditIssueSerializer,
    SearchConsoleConnectionSerializer, SearchAnalyticsDataSerializer
)


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


class SearchAnalyticsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for SearchAnalyticsData operations.
    
    Security & Ownership:
    1. Requires authentication on all actions.
    2. Queryset is strictly filtered by `connection__project__owner == request.user`.
    3. Cross-user access returns 404 Not Found.
    4. Supports ownership-safe filtering by project_id, connection_id, date, start_date,
       end_date, query, page, country, and device.
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

        return queryset



