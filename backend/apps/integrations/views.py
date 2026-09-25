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
    ProjectClarityConnection,
    ProjectGTMConnection,
)
from apps.integrations.serializers import (
    IntegrationStatusSerializer,
    SearchConsolePropertySerializer,
    SearchConsoleAssociateSerializer,
    GA4PropertySerializer,
    GA4AssociateSerializer,
    ClarityProjectSerializer,
    ClarityAssociateSerializer,
    OAuthCallbackRequestSerializer,
    GTMContainerSerializer,
    GTMAssociateSerializer,
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
from apps.integrations.services.clarity import (
    ClarityIntegrationService,
    ClarityError,
    ClarityNotConnectedError,
    ClarityCredentialsError,
    ClarityRateLimitError,
    ClarityApiError,
    ClarityProjectNotFoundError,
)
from apps.integrations.services.gtm import (
    GTMIntegrationService,
    GTMError,
    GTMNotConnectedError,
    GTMScopeMissingError,
    GTMCredentialsError,
    GTMRateLimitError,
    GTMApiError,
    GTMProjectNotFoundError,
)
from apps.subscriptions.permissions import CanAccessGSC, CanAccessGA4, CanAccessClarity, CanAccessGTM

logger = logging.getLogger(__name__)


class CanAccessGoogleIntegrations(permissions.BasePermission):
    """
    Permission check requiring that the user has an active plan entitled to
    either Google Search Console, Google Analytics 4, or Google Tag Manager.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from apps.subscriptions.services import PlanEntitlementService
        from apps.subscriptions.models import FeatureCode
        can_gsc = PlanEntitlementService.can_use_feature(request.user, FeatureCode.GSC)
        can_ga4 = PlanEntitlementService.can_use_feature(request.user, FeatureCode.GA4)
        can_gtm = PlanEntitlementService.can_use_feature(request.user, FeatureCode.GTM)
        if not (can_gsc or can_ga4 or can_gtm):
            PlanEntitlementService.check_can_use_feature(request.user, FeatureCode.GTM)
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
                'has_gtm_scope': conn.has_gtm_scope if conn.provider == IntegrationProvider.GOOGLE else False,
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
                'has_gtm_scope': False,
            }

        # Ensure microsoft entry exists even if not yet connected
        if IntegrationProvider.MICROSOFT not in results:
            results[IntegrationProvider.MICROSOFT] = {
                'connected': False,
                'status': IntegrationStatus.DISCONNECTED,
                'account_email': None,
                'account_name': None,
                'scopes': [],
                'connected_at': None,
                'updated_at': None,
                'has_valid_credentials': False,
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

                clarity_conn = ProjectClarityConnection.objects.filter(
                    project_id=project_id,
                    project__owner=request.user,
                    is_connected=True
                ).first()
                if clarity_conn:
                    results['project_clarity'] = {
                        'clarity_project_id': clarity_conn.clarity_project_id,
                        'name': clarity_conn.name,
                        'website_url': clarity_conn.website_url,
                        'is_connected': clarity_conn.is_connected,
                        'connected_at': clarity_conn.connected_at,
                    }
                else:
                    results['project_clarity'] = None

                gtm_conn = ProjectGTMConnection.objects.filter(
                    project_id=project_id,
                    project__owner=request.user,
                    is_connected=True
                ).first()
                if gtm_conn:
                    results['project_gtm'] = {
                        'account_id': gtm_conn.account_id,
                        'container_id': gtm_conn.container_id,
                        'container_public_id': gtm_conn.container_public_id,
                        'name': gtm_conn.name,
                        'usage_context': gtm_conn.usage_context,
                        'is_connected': gtm_conn.is_connected,
                        'connected_at': gtm_conn.connected_at,
                    }
                else:
                    results['project_gtm'] = None
            except (ValueError, TypeError):
                results['project_ga4'] = None
                results['project_clarity'] = None
                results['project_gtm'] = None

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


class MicrosoftClarityConnectView(APIView):
    """
    Initiate Microsoft OAuth2 connection flow or directly connect Microsoft Clarity account.
    (GET/POST /api/integrations/microsoft/clarity/connect/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessClarity]

    def get(self, request):
        redirect_uri = request.query_params.get('redirect_uri')
        try:
            auth_url = ClarityIntegrationService.get_authorization_url(
                user=request.user,
                redirect_uri=redirect_uri
            )
            return Response({'authorization_url': auth_url}, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response(
                {'detail': f"Microsoft OAuth configuration error: {str(exc)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as exc:
            logger.error(f"[MicrosoftClarityConnectView] Error generating authorization URL: {exc}")
            return Response(
                {'detail': f"Failed to initiate Microsoft connection: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """
        Directly connect or update Microsoft Clarity account with email/name or initial projects.
        """
        account_email = request.data.get('account_email')
        account_name = request.data.get('account_name')
        projects = request.data.get('projects')

        conn = ClarityIntegrationService.connect_account(
            user=request.user,
            account_email=account_email,
            account_name=account_name,
            projects=projects if isinstance(projects, list) else None,
        )
        serializer = IntegrationStatusSerializer(conn)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MicrosoftClarityCallbackView(APIView):
    """
    Handle Microsoft OAuth2 callback with authorization code and state token.
    (GET/POST /api/integrations/microsoft/clarity/callback/)
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
            desc = validated.get('error_description') or error
            logger.warning(f"[MicrosoftClarityCallbackView] Microsoft OAuth error: {error} - {desc}")
            return Response(
                {'detail': f"Microsoft authorization denied: {desc}", 'code': 'OAUTH_DENIED'},
                status=status.HTTP_400_BAD_REQUEST
            )

        code = validated.get('code')
        state = validated.get('state')
        redirect_uri = validated.get('redirect_uri') or None

        if not code or not state:
            return Response(
                {'detail': "Missing 'code' or 'state' parameter in OAuth callback.", 'code': 'MISSING_PARAMS'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            connection = ClarityIntegrationService.exchange_code_for_tokens(
                code=code,
                state=state,
                redirect_uri=redirect_uri
            )
            serializer = IntegrationStatusSerializer(connection)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except InvalidOAuthStateError as exc:
            return Response({'detail': str(exc), 'code': 'INVALID_STATE'}, status=status.HTTP_400_BAD_REQUEST)
        except ClarityCredentialsError as exc:
            return Response({'detail': str(exc), 'code': 'EXCHANGE_FAILED'}, status=status.HTTP_400_BAD_REQUEST)
        except ClarityApiError as exc:
            return Response({'detail': str(exc), 'code': 'PROVIDER_ERROR'}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            logger.error(f"[MicrosoftClarityCallbackView] Unexpected error: {exc}")
            return Response(
                {'detail': "An unexpected error occurred processing Microsoft callback."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MicrosoftClarityDisconnectView(APIView):
    """
    Safely disconnect user's Microsoft Clarity connection and clear credentials.
    (POST /api/integrations/microsoft/clarity/disconnect/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessClarity]

    def post(self, request):
        ClarityIntegrationService.disconnect(request.user)
        return Response({'detail': "Microsoft Clarity disconnected successfully."}, status=status.HTTP_200_OK)


class MicrosoftClarityProjectsView(APIView):
    """
    Retrieve accessible Microsoft Clarity projects for the connected user.
    (GET /api/integrations/microsoft/clarity/projects/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessClarity]

    def get(self, request):
        try:
            projects = ClarityIntegrationService.list_projects(user=request.user)
            serializer = ClarityProjectSerializer(projects, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ClarityNotConnectedError as exc:
            return Response({'code': 'CLARITY_NOT_CONNECTED', 'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ClarityCredentialsError as exc:
            return Response({'code': 'CLARITY_AUTH_ERROR', 'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ClarityRateLimitError as exc:
            return Response({'code': 'CLARITY_RATE_LIMIT', 'detail': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ClarityApiError as exc:
            return Response({'code': 'CLARITY_API_ERROR', 'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            logger.error(f"[MicrosoftClarityProjectsView] Error: {exc}")
            return Response(
                {'detail': f"Failed to retrieve Microsoft Clarity projects: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MicrosoftClarityAssociatePropertyView(APIView):
    """
    Associate an accessible Microsoft Clarity project with a DoxaRank project.
    (POST /api/integrations/microsoft/clarity/associate/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessClarity]

    def post(self, request):
        serializer = ClarityAssociateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        try:
            result = ClarityIntegrationService.associate_project(
                user=request.user,
                project_id=validated['project_id'],
                clarity_project_id=validated['clarity_project_id'],
                name=validated.get('name'),
                website=validated.get('website'),
                api_token=validated.get('api_token'),
            )
            return Response(result, status=status.HTTP_200_OK)
        except ClarityNotConnectedError as exc:
            return Response({'code': 'CLARITY_NOT_CONNECTED', 'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ClarityProjectNotFoundError as exc:
            return Response({'code': 'PROJECT_NOT_FOUND', 'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ClarityCredentialsError as exc:
            return Response({'code': 'CLARITY_AUTH_ERROR', 'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ClarityRateLimitError as exc:
            return Response({'code': 'CLARITY_RATE_LIMIT', 'detail': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ClarityApiError as exc:
            return Response({'code': 'CLARITY_API_ERROR', 'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            logger.error(f"[MicrosoftClarityAssociatePropertyView] Error: {exc}")
            return Response(
                {'detail': f"Failed to associate Microsoft Clarity project: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MicrosoftClarityProjectConnectionView(APIView):
    """
    Retrieve active Clarity connection for a specific DoxaRank Project.
    (GET /api/integrations/microsoft/clarity/project/?project_id=<id>)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessClarity]

    def get(self, request):
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response({'detail': "project_id query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            info = ClarityIntegrationService.get_project_connection(user=request.user, project_id=int(project_id))
            if not info:
                return Response(
                    {'is_connected': False, 'detail': "No Microsoft Clarity project linked to this project."},
                    status=status.HTTP_200_OK
                )
            return Response(info, status=status.HTTP_200_OK)
        except (ValueError, TypeError):
            return Response({'detail': "Invalid project_id."}, status=status.HTTP_400_BAD_REQUEST)


class GTMContainersView(APIView):
    """
    Retrieve user's accessible Google Tag Manager (GTM) containers via Google API.
    Requires authentication and GTM subscription entitlement.
    (GET /api/integrations/google/gtm/containers/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGTM]

    def get(self, request):
        try:
            containers = GTMIntegrationService.list_containers(request.user)
            serializer = GTMContainerSerializer(containers, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except GTMNotConnectedError as exc:
            return Response({'code': 'NOT_CONNECTED', 'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except GTMScopeMissingError as exc:
            return Response({'code': 'GTM_SCOPE_MISSING', 'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except GTMCredentialsError as exc:
            return Response({'code': 'CREDENTIALS_INVALID', 'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        except GTMRateLimitError as exc:
            return Response({'code': 'RATE_LIMIT_EXCEEDED', 'detail': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except GTMApiError as exc:
            return Response({'code': 'GOOGLE_API_ERROR', 'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            logger.error(f"[GTMContainersView] Error: {exc}")
            return Response(
                {'detail': f"Failed to retrieve GTM containers: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GTMAssociateContainerView(APIView):
    """
    Associate a verified GTM container with a user's DoxaRank Project.
    Requires authentication and GTM subscription entitlement.
    (POST /api/integrations/google/gtm/associate/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGTM]

    def post(self, request):
        serializer = GTMAssociateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        try:
            result = GTMIntegrationService.associate_project_container(
                user=request.user,
                project_id=validated['project_id'],
                container_id=validated['container_id'],
                account_id=validated.get('account_id'),
                container_public_id=validated.get('container_public_id'),
                name=validated.get('name'),
                usage_context=validated.get('usage_context'),
            )
            return Response(result, status=status.HTTP_200_OK)
        except GTMScopeMissingError as exc:
            return Response({'code': 'GTM_SCOPE_MISSING', 'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except GTMProjectNotFoundError as exc:
            return Response({'code': 'PROJECT_NOT_FOUND', 'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except GTMError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(f"[GTMAssociateContainerView] Error: {exc}")
            return Response(
                {'detail': f"Failed to associate GTM container: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GTMProjectConnectionView(APIView):
    """
    Retrieve active GTM connection for a specific DoxaRank Project.
    (GET /api/integrations/google/gtm/project/?project_id=<id>)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGTM]

    def get(self, request):
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response({'detail': "project_id query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            info = GTMIntegrationService.get_project_connection(user=request.user, project_id=int(project_id))
            if not info:
                return Response(
                    {'is_connected': False, 'detail': "No GTM container linked to this project."},
                    status=status.HTTP_200_OK
                )
            return Response(info, status=status.HTTP_200_OK)
        except (ValueError, TypeError):
            return Response({'detail': "Invalid project_id."}, status=status.HTTP_400_BAD_REQUEST)


class GTMDisconnectProjectView(APIView):
    """
    Disconnect GTM container from a specific DoxaRank Project.
    (POST /api/integrations/google/gtm/disconnect/)
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessGTM]

    def post(self, request):
        project_id = request.data.get('project_id')
        if not project_id:
            return Response({'detail': "project_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            disconnected = GTMIntegrationService.disconnect_project(user=request.user, project_id=int(project_id))
            return Response({'disconnected': disconnected}, status=status.HTTP_200_OK)
        except GTMProjectNotFoundError as exc:
            return Response({'code': 'PROJECT_NOT_FOUND', 'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (ValueError, TypeError):
            return Response({'detail': "Invalid project_id."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(f"[GTMDisconnectProjectView] Error: {exc}")
            return Response({'detail': f"Failed to disconnect GTM: {str(exc)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


