import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from apps.subscriptions.permissions import CanAccessBasicSEOTools
from .serializers import (
    MetaTagInputSerializer,
    SchemaInputSerializer,
    SocialPreviewInputSerializer,
    RobotsToolInputSerializer,
    SitemapToolInputSerializer,
    HreflangInputSerializer,
)
from .services import SEOToolsService

logger = logging.getLogger(__name__)


class MetaTagGeneratorView(APIView):
    """
    POST /api/seo/tools/meta/
    Generates standard HTML meta tags with length guidance.
    Enforces BASIC_SEO_TOOLS entitlement and Free daily quota.
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessBasicSEOTools]

    def post(self, request, *args, **kwargs):
        serializer = MetaTagInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = SEOToolsService.generate_meta_tags(request.user, serializer.validated_data)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SchemaGeneratorView(APIView):
    """
    POST /api/seo/tools/schema/
    Generates Schema.org JSON-LD scripts for vetted types:
    LocalBusiness, Article, Product, FAQ, BreadcrumbList.
    Enforces BASIC_SEO_TOOLS entitlement and Free daily quota.
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessBasicSEOTools]

    def post(self, request, *args, **kwargs):
        serializer = SchemaInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        schema_type = serializer.validated_data['schema_type']
        schema_data = serializer.validated_data['data']

        try:
            result = SEOToolsService.generate_schema(request.user, schema_type, schema_data)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SocialPreviewGeneratorView(APIView):
    """
    POST /api/seo/tools/social-preview/
    Generates Open Graph and Twitter Card tags and preview data.
    SSRF-safe: does not issue server-side network requests.
    Enforces BASIC_SEO_TOOLS entitlement and Free daily quota.
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessBasicSEOTools]

    def post(self, request, *args, **kwargs):
        serializer = SocialPreviewInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = SEOToolsService.generate_social_preview(request.user, serializer.validated_data)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class RobotsToolView(APIView):
    """
    POST /api/seo/tools/robots/
    Generates or tests robots.txt access rules with syntax validation.
    Enforces BASIC_SEO_TOOLS entitlement and Free daily quota.
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessBasicSEOTools]

    def post(self, request, *args, **kwargs):
        serializer = RobotsToolInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = SEOToolsService.process_robots_tool(request.user, serializer.validated_data)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SitemapToolView(APIView):
    """
    POST /api/seo/tools/sitemap/
    Generates official XML sitemaps or validates sitemap structure locally.
    Enforces BASIC_SEO_TOOLS entitlement and Free daily quota.
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessBasicSEOTools]

    def post(self, request, *args, **kwargs):
        serializer = SitemapToolInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = SEOToolsService.process_sitemap_tool(request.user, serializer.validated_data)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class HreflangToolView(APIView):
    """
    POST /api/seo/tools/hreflang/
    Builds localized alternate annotations for English, Amharic, Afaan Oromo, and x-default.
    Enforces BASIC_SEO_TOOLS entitlement and Free daily quota.
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessBasicSEOTools]

    def post(self, request, *args, **kwargs):
        serializer = HreflangInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = SEOToolsService.generate_hreflang(request.user, serializer.validated_data)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SEOToolsQuotaStatusView(APIView):
    """
    GET /api/seo/tools/status/
    Returns the user's daily usage consumption and limits without consuming quota.
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessBasicSEOTools]

    def get(self, request, *args, **kwargs):
        data = SEOToolsService.get_user_tool_quota_status(request.user)
        return Response(data, status=status.HTTP_200_OK)
