"""فیلترهای ماژول هویت."""

import django_filters as filters

from apps.identity.models import AuditLog, Person, UserAccount, UserRoleAssignment


class PersonFilter(filters.FilterSet):
    full_name = filters.CharFilter(
        method="filter_full_name", label="جست‌وجو در نام کامل"
    )
    birth_date_from = filters.DateFilter(field_name="birth_date", lookup_expr="gte")
    birth_date_to = filters.DateFilter(field_name="birth_date", lookup_expr="lte")
    has_user_account = filters.BooleanFilter(
        method="filter_has_user_account", label="دارای حساب کاربری"
    )

    class Meta:
        model = Person
        fields = ("gender", "status", "nationality", "national_id")

    def filter_full_name(self, queryset, name, value):
        from django.db.models import Q

        for token in value.split():
            queryset = queryset.filter(
                Q(first_name__icontains=token) | Q(last_name__icontains=token)
            )
        return queryset

    def filter_has_user_account(self, queryset, name, value):
        return queryset.filter(user_account__isnull=not value)


class UserAccountFilter(filters.FilterSet):
    role_code = filters.CharFilter(
        field_name="role_assignments__role__code", label="کد نقش"
    )
    scope_id = filters.UUIDFilter(
        field_name="role_assignments__scope_id", label="شناسه دامنه"
    )

    class Meta:
        model = UserAccount
        fields = ("status", "is_active", "mfa_enabled", "must_change_password")


class UserRoleAssignmentFilter(filters.FilterSet):
    role_code = filters.CharFilter(field_name="role__code")
    active_on = filters.DateFilter(
        method="filter_active_on", label="فعال در تاریخ مشخص"
    )

    class Meta:
        model = UserRoleAssignment
        fields = ("user", "role", "scope_type", "scope_id", "status")

    def filter_active_on(self, queryset, name, value):
        from django.db.models import Q

        return queryset.filter(effective_from__lte=value).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=value)
        )


class AuditLogFilter(filters.FilterSet):
    occurred_from = filters.DateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_to = filters.DateTimeFilter(field_name="occurred_at", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = (
            "action",
            "entity_type",
            "entity_id",
            "actor_user_id",
            "correlation_id",
            "classification",
        )
