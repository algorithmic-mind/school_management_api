"""مسیرهای احراز هویت."""

from django.urls import path

from apps.identity.views import (
    CurrentUserView,
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RefreshTokenView,
    RevokeSessionsView,
    WorkingContextView,
)

urlpatterns = [
    path("token/", LoginView.as_view(), name="auth-token"),
    path("token/refresh/", RefreshTokenView.as_view(), name="auth-token-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
    path("contexts/", WorkingContextView.as_view(), name="auth-contexts"),
    path("sessions/revoke/", RevokeSessionsView.as_view(), name="auth-revoke-sessions"),
    path("password/change/", PasswordChangeView.as_view(), name="auth-password-change"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
]
