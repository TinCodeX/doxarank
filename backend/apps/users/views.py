from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    UserSerializer,
    RegisterSerializer,
    LoginSerializer,
    LogoutSerializer
)


def get_tokens_for_user(user):
    """
    Generate access and refresh tokens for a given user.
    """
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class RegisterView(APIView):
    """
    POST /api/auth/register/
    Registers a new user and immediately returns JWT tokens with user profile.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            tokens = get_tokens_for_user(user)
            user_data = UserSerializer(user).data
            return Response(
                {
                    'user': user_data,
                    'tokens': tokens,
                    'message': 'Registration successful.'
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    POST /api/auth/login/
    Authenticates existing user with email and password and returns JWT tokens.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            tokens = get_tokens_for_user(user)
            user_data = UserSerializer(user).data
            return Response(
                {
                    'user': user_data,
                    'tokens': tokens,
                    'message': 'Login successful.'
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Blacklists the given refresh token. Requires an authenticated session.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {'detail': 'Successfully logged out.'},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    """
    GET /api/auth/me/
    Returns the authenticated user's profile details.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ContactMessageCreateView(APIView):
    """
    POST /api/contact/ or /api/auth/contact/
    Handles inbound messages from the marketing site contact page.
    Persists inquiries to database and dispatches email notifications.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from .serializers import ContactMessageSerializer
        from .services import send_contact_emails
        from .tasks import send_contact_email_task
        import logging
        logger = logging.getLogger(__name__)

        serializer = ContactMessageSerializer(data=request.data)
        if serializer.is_valid():
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

            instance = serializer.save(
                ip_address=ip_address,
                user_agent=user_agent
            )

            # Dispatch emails: synchronous in DEBUG for immediate execution & console logs; async Celery in production
            email_dispatched = False
            from django.conf import settings
            try:
                if getattr(settings, 'DEBUG', False) or getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
                    success, _ = send_contact_emails(instance)
                    email_dispatched = success
                else:
                    send_contact_email_task.delay(instance.id)
                    email_dispatched = True
            except Exception as e:
                logger.info(f"Async email dispatch unavailable for contact #{instance.id}, running sync: {e}")
                try:
                    success, _ = send_contact_emails(instance)
                    email_dispatched = success
                except Exception as inner_e:
                    logger.error(f"Synchronous email dispatch failed for contact #{instance.id}: {inner_e}")


            return Response(
                {
                    'success': True,
                    'message': 'Thank you! Your message has been received. Our team will get back to you shortly.',
                    'data': serializer.data,
                    'email_dispatched': email_dispatched,
                },
                status=status.HTTP_201_CREATED
            )

        return Response(
            {
                'success': False,
                'message': 'Validation failed. Please check the entered fields.',
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )

