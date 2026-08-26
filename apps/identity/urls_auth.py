"""مسیرهای احراز هویت."""

from django.urls import path

from apps.identity.views import (
    CurrentUserView,
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetRequestView,
    RefreshTokenView,
)

urlpatterns = [
    path("token/", LoginView.as_view(), name="auth-token"),
    path("token/refresh/", RefreshTokenView.as_view(), name="auth-token-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
    path("password/change/", PasswordChangeView.as_view(), name="auth-password-change"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
]
