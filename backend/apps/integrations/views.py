import logging
from urllib.parse import urlencode

from django.shortcuts import redirect
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.models import (
    IntegrationConnection,
    IntegrationProvider,
    IntegrationStatus,
    ProjectGA4Connection,
)
from apps.integrations.serializers import (
    IntegrationStatusSerializer,
    SearchConsolePropertySerializer,
    SearchConsoleAssociateSerializer,
    GA4PropertySerializer,
    GA4AssociateSerializer,
    OAuthCallbackRequestSerializer,
)
from apps.integrations.services.google_oauth import (
    GoogleOAuthIntegrationService,
    OAuthStateService,
    InvalidOAuthStateError,
    GoogleOAuthExchangeError,
)
from apps.integrations.services.search_console import (
    SearchConsoleIntegrationService,
    SearchConsoleError,
    SearchConsoleNotConnectedError,
    SearchConsoleCredentialsError,
    SearchConsoleApiError,
)
from apps.integrations.services.analytics import (
    GA4IntegrationService,
    GA4Error,
    GA4NotConnectedError,
    GA4ScopeMissingError,
    GA4CredentialsError,
    GA4RateLimitError,
    GA4ApiError,
)
from apps.subscriptions.permissions import CanAccessGSC, CanAccessGA4

logger = logging.getLogger(__name__)


class CanAccessGoogleIntegrations(permissions.BasePermission):
    """
    Permission check requiring that the user has an active plan entitled to
    either Google Search Console or Google Analytics 4.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from apps.subscriptions.services import PlanEntitlementService
        from apps.subscriptions.models import FeatureCode
        can_gsc = PlanEntitlementService.can_use_feature(request.user, FeatureCode.GSC)
        can_ga4 = PlanEntitlementService.can_use_feature(request.user, FeatureCode.GA4)
        if not (can_gsc or can_ga4):
            PlanEntitlementService.check_can_use_feature(request.user, FeatureCode.GA4)
        return True


class GoogleConnectView(APIView):
    """
    Initiate Google OAuth2 connection flow for the authenticated user.
    Requires authentication and an active subscription entitled to Google integrations.
    (GET /api/integrations/google/connect/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGoogleIntegrations]

    def get(self, request):
        redirect_uri = request.query_params.get('redirect_uri')
        try:
            auth_url = GoogleOAuthIntegrationService.get_authorization_url(
                user=request.user,
                redirect_uri=redirect_uri
            )
            return Response({'authorization_url': auth_url}, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response(
                {'detail': f"Google OAuth configuration error: {str(exc)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as exc:
            logger.error(f"[GoogleConnectView] Error generating authorization URL: {exc}")
            return Response(
                {'detail': f"Failed to initiate Google connection: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GoogleCallbackView(APIView):
    """
    Handle Google OAuth2 callback with authorization code and state token.
    Validates cryptographic state, exchanges authorization code, verifies identity,
    and securely stores encrypted tokens.
    (GET/POST /api/integrations/google/callback/)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return self._process_callback(request, data=request.query_params)

    def post(self, request):
        return self._process_callback(request, data=request.data)

    def _process_callback(self, request, data):
        serializer = OAuthCallbackRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        error = validated.get('error')
        if error:
            error_msg = (
                "Google authorization was denied by the user."
                if error in ['access_denied', 'consent_denied']
                else f"Google authorization error: {error}"
            )
            return Response({'detail': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        code = validated.get('code')
        state = validated.get('state')
        redirect_uri = validated.get('redirect_uri') or None

        if not code or not code.strip():
            return Response({'detail': "Authorization code is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not state or not state.strip():
            return Response({'detail': "OAuth state parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate cryptographic state token
        try:
            state_user, meta = OAuthStateService.verify_state(
                raw_state=state,
                expected_user=request.user if request.user.is_authenticated else None
            )
        except InvalidOAuthStateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Exchange code for tokens and verify Google user identity
        try:
            tokens = GoogleOAuthIntegrationService.exchange_code(code=code, redirect_uri=redirect_uri)
            user_identity = GoogleOAuthIntegrationService.fetch_user_identity(
                access_token=tokens.get('access_token')
            )
            connection = GoogleOAuthIntegrationService.save_or_update_connection(
                user=state_user,
                token_data=tokens,
                user_identity=user_identity
            )
            response_serializer = IntegrationStatusSerializer(connection)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        except GoogleOAuthExchangeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(f"[GoogleCallbackView] Unexpected error: {exc}")
            return Response(
                {'detail': f"An error occurred while connecting Google account: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class IntegrationStatusView(APIView):
    """
    Retrieve integration connection statuses for the authenticated user.
    (GET /api/integrations/status/)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        connections = IntegrationConnection.objects.filter(user=request.user)
        results = {}

        for conn in connections:
            results[conn.provider] = {
                'id': conn.id,
                'connected': conn.status == IntegrationStatus.CONNECTED,
                'status': conn.status,
                'account_email': conn.account_email,
                'account_name': conn.account_name,
                'scopes': conn.scopes,
                'connected_at': conn.connected_at,
                'updated_at': conn.updated_at,
                'has_valid_credentials': conn.has_valid_credentials,
                'has_analytics_scope': conn.has_analytics_scope if conn.provider == IntegrationProvider.GOOGLE else False,
            }

        # Ensure google entry exists even if not yet connected
        if IntegrationProvider.GOOGLE not in results:
            results[IntegrationProvider.GOOGLE] = {
                'connected': False,
                'status': IntegrationStatus.DISCONNECTED,
                'account_email': None,
                'account_name': None,
                'scopes': [],
                'connected_at': None,
                'updated_at': None,
                'has_valid_credentials': False,
                'has_analytics_scope': False,
            }

        project_id = request.query_params.get('project_id')
        if project_id:
            try:
                ga4_conn = ProjectGA4Connection.objects.filter(
                    project_id=project_id,
                    project__owner=request.user,
                    is_connected=True
                ).first()
                if ga4_conn:
                    results['project_ga4'] = {
                        'property_id': ga4_conn.property_id,
                        'display_name': ga4_conn.display_name,
                        'is_connected': ga4_conn.is_connected,
                        'connected_at': ga4_conn.connected_at,
                    }
                else:
                    results['project_ga4'] = None
            except (ValueError, TypeError):
                results['project_ga4'] = None

        return Response(results, status=status.HTTP_200_OK)


class GoogleDisconnectView(APIView):
    """
    Safely disconnect user's Google account and clear credentials.
    (POST /api/integrations/google/disconnect/)
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        disconnected = GoogleOAuthIntegrationService.disconnect(request.user)
        if disconnected:
            return Response({'detail': "Google account disconnected successfully."}, status=status.HTTP_200_OK)
        return Response({'detail': "No active Google connection found."}, status=status.HTTP_404_NOT_FOUND)


class SearchConsolePropertiesView(APIView):
    """
    Retrieve user's verified Search Console properties from Google.
    Requires authentication and GSC subscription entitlement.
    (GET /api/integrations/google/search-console/properties/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGSC]

    def get(self, request):
        try:
            properties = SearchConsoleIntegrationService.list_properties(request.user)
            serializer = SearchConsolePropertySerializer(properties, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except SearchConsoleNotConnectedError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except SearchConsoleCredentialsError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        except SearchConsoleApiError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            logger.error(f"[SearchConsolePropertiesView] Error: {exc}")
            return Response(
                {'detail': f"Failed to retrieve Search Console properties: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SearchConsoleAssociatePropertyView(APIView):
    """
    Associate a verified Search Console property with a user's DoxaRank Project.
    Requires authentication and GSC subscription entitlement.
    (POST /api/integrations/google/search-console/associate/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGSC]

    def post(self, request):
        serializer = SearchConsoleAssociateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        try:
            result = SearchConsoleIntegrationService.associate_project_property(
                user=request.user,
                project_id=validated['project_id'],
                site_url=validated['site_url'],
                permission_level=validated.get('permission_level', 'siteOwner')
            )
            return Response(result, status=status.HTTP_200_OK)
        except SearchConsoleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(f"[SearchConsoleAssociatePropertyView] Error: {exc}")
            return Response(
                {'detail': f"Failed to associate property: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GA4PropertiesView(APIView):
    """
    Retrieve user's accessible Google Analytics 4 (GA4) properties via Google API.
    Requires authentication and GA4 subscription entitlement.
    (GET /api/integrations/google/analytics/properties/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGA4]

    def get(self, request):
        try:
            properties = GA4IntegrationService.list_properties(request.user)
            serializer = GA4PropertySerializer(properties, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except GA4NotConnectedError as exc:
            return Response({'code': 'NOT_CONNECTED', 'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except GA4ScopeMissingError as exc:
            return Response({'code': 'ANALYTICS_SCOPE_MISSING', 'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except GA4CredentialsError as exc:
            return Response({'code': 'CREDENTIALS_INVALID', 'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        except GA4RateLimitError as exc:
            return Response({'code': 'RATE_LIMIT_EXCEEDED', 'detail': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except GA4ApiError as exc:
            return Response({'code': 'GOOGLE_API_ERROR', 'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            logger.error(f"[GA4PropertiesView] Error: {exc}")
            return Response(
                {'detail': f"Failed to retrieve GA4 properties: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GA4AssociatePropertyView(APIView):
    """
    Associate a verified GA4 property with a user's DoxaRank Project.
    Requires authentication and GA4 subscription entitlement.
    (POST /api/integrations/google/analytics/associate/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGA4]

    def post(self, request):
        serializer = GA4AssociateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        try:
            result = GA4IntegrationService.associate_project_property(
                user=request.user,
                project_id=validated['project_id'],
                property_id=validated['property_id'],
                display_name=validated.get('display_name')
            )
            return Response(result, status=status.HTTP_200_OK)
        except GA4ScopeMissingError as exc:
            return Response({'code': 'ANALYTICS_SCOPE_MISSING', 'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except GA4Error as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(f"[GA4AssociatePropertyView] Error: {exc}")
            return Response(
                {'detail': f"Failed to associate GA4 property: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GA4ProjectConnectionView(APIView):
    """
    Retrieve active GA4 connection for a specific DoxaRank Project.
    (GET /api/integrations/google/analytics/project/?project_id=<id>)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGA4]

    def get(self, request):
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response({'detail': "project_id query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            info = GA4IntegrationService.get_project_connection(user=request.user, project_id=int(project_id))
            if not info:
                return Response({'is_connected': False, 'detail': "No GA4 property linked to this project."}, status=status.HTTP_200_OK)
            return Response(info, status=status.HTTP_200_OK)
        except (ValueError, TypeError):
            return Response({'detail': "Invalid project_id."}, status=status.HTTP_400_BAD_REQUEST)
