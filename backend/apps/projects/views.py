from rest_framework import viewsets, permissions
from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for Project resource.
    
    Security & Ownership:
    1. Requires authentication on all actions (IsAuthenticated).
    2. Enforces strict tenant isolation in get_queryset():
       A user can ONLY see, query, update, or delete projects where owner == request.user.
    3. In perform_create(), automatically binds owner to the authenticated user.
    """
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filter queryset so users can only ever access their own projects.
        Any attempt to access another user's project ID will return 404 Not Found.
        """
        return Project.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        """
        Automatically associate the newly created project with the authenticated user.
        Enforces subscription plan project quota limits.
        """
        from apps.subscriptions.services import PlanEntitlementService
        PlanEntitlementService.check_can_create_project(self.request.user)
        serializer.save(owner=self.request.user)
