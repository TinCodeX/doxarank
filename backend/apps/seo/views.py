from rest_framework import viewsets, permissions
from .models import Keyword, KeywordRanking, SiteAudit, AuditIssue
from .serializers import (
    KeywordSerializer, KeywordRankingSerializer,
    SiteAuditSerializer, AuditIssueSerializer
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

