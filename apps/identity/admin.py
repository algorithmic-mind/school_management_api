from django.apps import apps
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.identity.models import (
    AuditLog,
    Permission,
    Person,
    Role,
    UserAccount,
    UserRoleAssignment,
)


@admin.register(Person)
class PersonAdmin(SchoolModelAdmin):
    list_display = ("first_name", "last_name", "national_id", "gender", "status")
    search_fields = ("first_name", "last_name", "national_id")
    list_filter = ("gender", "status")


@admin.register(UserAccount)
class UserAccountAdmin(BaseUserAdmin):
    ordering = ("username",)
    list_display = ("username", "email", "mobile", "status", "is_active", "is_staff")
    list_filter = ("status", "is_active", "is_staff", "mfa_enabled")
    search_fields = ("username", "email", "mobile")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("هویت", {"fields": ("person", "tenant", "email", "mobile")}),
        ("وضعیت", {"fields": ("status", "is_active", "mfa_enabled", "mfa_method", "must_change_password")}),
        ("دسترسی", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("زمان‌ها", {"fields": ("last_login_at", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "password1", "password2")}),
    )


@admin.register(Permission)
class PermissionAdmin(SchoolModelAdmin):
    list_display = ("code", "module", "resource", "action", "is_sensitive")
    list_filter = ("module", "is_sensitive")
    search_fields = ("code", "title")


@admin.register(Role)
class RoleAdmin(SchoolModelAdmin):
    list_display = ("code", "title", "is_system", "requires_mfa")
    list_filter = ("is_system", "requires_mfa")
    filter_horizontal = ()
    search_fields = ("code", "title")


@admin.register(UserRoleAssignment)
class UserRoleAssignmentAdmin(SchoolModelAdmin):
    list_display = ("user", "role", "scope_type", "scope_id", "status", "effective_from")
    list_filter = ("status", "scope_type")


@admin.register(AuditLog)
class AuditLogAdmin(SchoolModelAdmin):
    list_display = ("occurred_at", "action", "entity_type", "actor_username", "correlation_id")
    list_filter = ("action", "entity_type")
    search_fields = ("entity_label", "actor_username", "correlation_id")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("identity").get_models())
