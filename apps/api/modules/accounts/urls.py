from django.urls import path

from .views import (
    CsrfTokenView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetVerificationCodeView,
    PasswordResetView,
    RegisterView,
    RegistrationClassListView,
    RegistrationVerificationCodeView,
)

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("register/", RegisterView.as_view(), name="auth-register"),
    path(
        "verification-codes/registration/",
        RegistrationVerificationCodeView.as_view(),
        name="auth-registration-code",
    ),
    path(
        "verification-codes/password-reset/",
        PasswordResetVerificationCodeView.as_view(),
        name="auth-password-reset-code",
    ),
    path("password-reset/", PasswordResetView.as_view(), name="auth-password-reset"),
    path(
        "registration-classes/",
        RegistrationClassListView.as_view(),
        name="auth-registration-classes",
    ),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
]
