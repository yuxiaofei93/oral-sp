from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from modules.core.observability import current_request_id
from modules.teaching.models import ClassGroup

from .models import User, VerificationPurpose
from .serializers import (
    LoginSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    RegistrationClassSerializer,
    UserSerializer,
    VerificationCodeRequestSerializer,
)
from .verification import (
    CODE_TTL_SECONDS,
    VerificationCodeCooldownError,
    VerificationEmailError,
    send_verification_email,
)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class RegistrationClassListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        classes = ClassGroup.objects.filter(is_active=True).select_related(
            "created_by"
        ).order_by("code")
        return Response(RegistrationClassSerializer(classes, many=True).data)


def verification_error_response(error):
    if isinstance(error, VerificationCodeCooldownError):
        response = Response(
            {"detail": str(error), "retry_after": error.retry_after},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        response["Retry-After"] = str(error.retry_after)
        return response
    if isinstance(error, VerificationEmailError):
        return Response(
            {"detail": str(error), "request_id": current_request_id()},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_protect, name="dispatch")
class RegistrationVerificationCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verification_code"

    def post(self, request):
        serializer = VerificationCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        if User.objects.filter(email=email).exists():
            return Response(
                {"detail": "该邮箱已经注册。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            send_verification_email(
                email=email,
                purpose=VerificationPurpose.REGISTRATION,
            )
        except (VerificationCodeCooldownError, VerificationEmailError) as error:
            return verification_error_response(error)
        return Response({"detail": "验证码已发送。", "expires_in": CODE_TTL_SECONDS})


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetVerificationCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verification_code"

    def post(self, request):
        serializer = VerificationCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        if User.objects.filter(email=email, is_active=True).exists():
            try:
                send_verification_email(
                    email=email,
                    purpose=VerificationPurpose.PASSWORD_RESET,
                )
            except (VerificationCodeCooldownError, VerificationEmailError) as error:
                return verification_error_response(error)
        return Response({"detail": "如果该邮箱已注册，验证码将发送到邮箱。"})


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "密码已重置，请使用新密码登录。"})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None or not user.is_active:
            return Response(
                {"detail": "邮箱或密码错误。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
