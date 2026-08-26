"""سریالایزرهای ماژول هویت و دسترسی."""

from __future__ import annotations

from django.contrib.auth import authenticate
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.serializers import AUDIT_FIELDS
from apps.identity.models import (
    AccessReview,
    AccessReviewItem,
    Address,
    AuditLog,
    ContactPoint,
    Permission,
    Person,
    PersonAddress,
    PersonDocument,
    Role,
    RolePermission,
    UserAccount,
    UserRoleAssignment,
)


# ---------------------------------------------------------------------------
# شخص و اطلاعات تماس
# ---------------------------------------------------------------------------
class ContactPointSerializer(serializers.ModelSerializer):
    contact_type_display = serializers.CharField(
        source="get_contact_type_display", read_only=True
    )

    class Meta:
        model = ContactPoint
        fields = (
            "id",
            "person",
            "contact_type",
            "contact_type_display",
            "value",
            "is_primary",
            "is_verified",
            "verified_at",
            "label",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "is_verified", "verified_at", "created_at", "updated_at", "version")


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = (
            "id",
            "country",
            "province",
            "city",
            "district",
            "postal_code",
            "line",
            "latitude",
            "longitude",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class PersonAddressSerializer(serializers.ModelSerializer):
    address_detail = AddressSerializer(source="address", read_only=True)

    class Meta:
        model = PersonAddress
        fields = (
            "id",
            "person",
            "address",
            "address_detail",
            "address_type",
            "effective_from",
            "effective_to",
        )
        read_only_fields = ("id",)


class PersonDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonDocument
        fields = (
            "id",
            "person",
            "document_type",
            "title",
            "file",
            "sha256",
            "classification",
            "verification_status",
            "verified_at",
            "issued_on",
            "expires_at",
            "purpose",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "sha256",
            "verification_status",
            "verified_at",
            "created_at",
            "updated_at",
            "version",
        )


class PersonListSerializer(serializers.ModelSerializer):
    """نمای سبک برای فهرست و جست‌وجو."""

    full_name = serializers.CharField(read_only=True)
    gender_display = serializers.CharField(source="get_gender_display", read_only=True)

    class Meta:
        model = Person
        fields = (
            "id",
            "first_name",
            "last_name",
            "full_name",
            "national_id",
            "birth_date",
            "gender",
            "gender_display",
            "status",
        )


class PersonSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    contact_points = ContactPointSerializer(many=True, read_only=True)
    addresses = PersonAddressSerializer(
        source="person_addresses", many=True, read_only=True
    )
    has_user_account = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = (
            "id",
            "national_id",
            "passport_no",
            "first_name",
            "last_name",
            "full_name",
            "father_name",
            "birth_date",
            "birth_place",
            "gender",
            "nationality",
            "preferred_language",
            "photo",
            "accessibility_needs",
            "status",
            "contact_points",
            "addresses",
            "has_user_account",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    @extend_schema_field(serializers.BooleanField())
    def get_has_user_account(self, obj) -> bool:
        return hasattr(obj, "user_account")

    def validate(self, attrs):
        """
        بخش ۷.۲: حداقل یکی از شناسه‌های معتبر هویتی لازم است؛
        استثنا برای اتباع/پرونده موقت با دلیل مجاز است.
        """
        national_id = attrs.get("national_id", getattr(self.instance, "national_id", ""))
        passport_no = attrs.get("passport_no", getattr(self.instance, "passport_no", ""))
        if not national_id and not passport_no:
            raise serializers.ValidationError(
                {
                    "national_id": "حداقل یکی از «شماره ملی» یا «شماره گذرنامه» باید تکمیل شود."
                }
            )
        return attrs


# ---------------------------------------------------------------------------
# مجوز، نقش و انتساب
# ---------------------------------------------------------------------------
class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = (
            "id",
            "code",
            "resource",
            "action",
            "title",
            "module",
            "description",
            "is_sensitive",
        )
        read_only_fields = ("id",)


class RoleSerializer(serializers.ModelSerializer):
    permission_codes = serializers.SlugRelatedField(
        source="permissions",
        slug_field="code",
        many=True,
        queryset=Permission.objects.all(),
        required=False,
        help_text="فهرست کدهای مجوز، مثلاً [\"student.read\", \"student.create\"]",
    )
    permission_count = serializers.IntegerField(
        source="permissions.count", read_only=True
    )

    class Meta:
        model = Role
        fields = (
            "id",
            "code",
            "title",
            "description",
            "is_system",
            "requires_mfa",
            "allowed_scope_types",
            "permission_codes",
            "permission_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "is_system", "created_at", "updated_at", "version")

    def update(self, instance, validated_data):
        if instance.is_system and "permissions" in validated_data:
            raise serializers.ValidationError(
                {"permission_codes": "مجوزهای نقش سیستمی قابل تغییر نیست."}
            )
        return super().update(instance, validated_data)


class UserRoleAssignmentSerializer(serializers.ModelSerializer):
    role_code = serializers.CharField(source="role.code", read_only=True)
    role_title = serializers.CharField(source="role.title", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    is_currently_effective = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserRoleAssignment
        fields = (
            "id",
            "user",
            "username",
            "role",
            "role_code",
            "role_title",
            "scope_type",
            "scope_id",
            "status",
            "effective_from",
            "effective_to",
            "is_currently_effective",
            "grant_reason",
            "revoked_at",
            "revoke_reason",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "revoked_at",
            "created_at",
            "updated_at",
            "version",
        )

    def validate(self, attrs):
        role = attrs.get("role") or getattr(self.instance, "role", None)
        scope_type = attrs.get("scope_type") or getattr(self.instance, "scope_type", None)
        if role and role.allowed_scope_types and scope_type:
            if scope_type not in role.allowed_scope_types:
                raise serializers.ValidationError(
                    {
                        "scope_type": (
                            f"نقش «{role.title}» فقط در دامنه‌های "
                            f"{', '.join(role.allowed_scope_types)} قابل انتساب است."
                        )
                    }
                )
        effective_from = attrs.get("effective_from") or getattr(
            self.instance, "effective_from", None
        )
        effective_to = attrs.get("effective_to") or getattr(
            self.instance, "effective_to", None
        )
        if effective_from and effective_to and effective_to < effective_from:
            raise serializers.ValidationError(
                {"effective_to": "تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد."}
            )
        return attrs


# ---------------------------------------------------------------------------
# حساب کاربری
# ---------------------------------------------------------------------------
class UserAccountSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    person_detail = PersonListSerializer(source="person", read_only=True)
    role_assignments = UserRoleAssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = UserAccount
        fields = (
            "id",
            "username",
            "email",
            "mobile",
            "person",
            "person_detail",
            "display_name",
            "status",
            "mfa_enabled",
            "mfa_method",
            "must_change_password",
            "is_active",
            "is_staff",
            "last_login_at",
            "date_joined",
            "role_assignments",
        )
        read_only_fields = (
            "id",
            "last_login_at",
            "date_joined",
            "is_staff",
            "role_assignments",
        )


class UserAccountCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=10, required=False)

    class Meta:
        model = UserAccount
        fields = (
            "id",
            "username",
            "email",
            "mobile",
            "person",
            "status",
            "password",
            "mfa_enabled",
            "mfa_method",
        )
        read_only_fields = ("id",)

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = UserAccount(**validated_data)
        if password:
            user.set_password(password)
            user.password_changed_at = timezone.now()
        else:
            user.set_unusable_password()
            user.must_change_password = True
        user.save()
        return user


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=10)

    def validate_new_password(self, value):
        from django.contrib.auth.password_validation import validate_password

        validate_password(value, self.context["request"].user)
        return value

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("رمز عبور فعلی درست نیست.")
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    درخواست بازیابی رمز.

    بخش ۱۵.۱: «جلوگیری از افشای وجود حساب» — پاسخ همیشه یکسان است.
    """

    identifier = serializers.CharField(
        help_text="نام کاربری، ایمیل یا تلفن همراه"
    )


# ---------------------------------------------------------------------------
# ورود و Context
# ---------------------------------------------------------------------------
class ScopeContextSerializer(serializers.Serializer):
    """یک محیط کاری مجاز برای کاربر (بخش ۵.۲ سند فرانت)."""

    roleCode = serializers.CharField()
    roleTitle = serializers.CharField()
    scopeType = serializers.CharField()
    scopeId = serializers.UUIDField(allow_null=True)


class LoginSerializer(serializers.Serializer):
    """بدنه ورود."""

    username = serializers.CharField(help_text="نام کاربری یا تلفن همراه")
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class TokenPairSerializer(serializers.Serializer):
    """پاسخ ورود موفق."""

    access = serializers.CharField(help_text="توکن دسترسی (عمر کوتاه)")
    refresh = serializers.CharField(help_text="توکن تازه‌سازی")
    expiresIn = serializers.IntegerField(help_text="عمر توکن دسترسی به ثانیه")
    mustChangePassword = serializers.BooleanField()
    mfaRequired = serializers.BooleanField()


class ContextTokenObtainPairSerializer(TokenObtainPairSerializer):
    """توکن را با اطلاعات Tenant و نقش‌ها غنی می‌کند."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["tenant_id"] = str(user.tenant_id) if user.tenant_id else None
        token["person_id"] = str(user.person_id) if user.person_id else None
        token["username"] = user.username
        token["roles"] = sorted(
            {a["role__code"] for a in user.get_effective_scopes()}
        )
        return token


class CurrentUserSerializer(serializers.Serializer):
    """پروفایل کاربر جاری به همراه مجوزها و محیط‌های کاری مجاز."""

    id = serializers.UUIDField()
    username = serializers.CharField()
    displayName = serializers.CharField()
    email = serializers.CharField(allow_blank=True)
    mobile = serializers.CharField(allow_blank=True)
    personId = serializers.UUIDField(allow_null=True)
    tenantId = serializers.UUIDField(allow_null=True)
    status = serializers.CharField()
    mfaEnabled = serializers.BooleanField()
    mustChangePassword = serializers.BooleanField()
    isSuperuser = serializers.BooleanField()
    roles = serializers.ListField(child=serializers.CharField())
    permissions = serializers.ListField(child=serializers.CharField())
    contexts = ScopeContextSerializer(many=True)


# ---------------------------------------------------------------------------
# بازبینی دسترسی و ممیزی
# ---------------------------------------------------------------------------
class AccessReviewItemSerializer(serializers.ModelSerializer):
    assignment_detail = UserRoleAssignmentSerializer(
        source="assignment", read_only=True
    )

    class Meta:
        model = AccessReviewItem
        fields = (
            "id",
            "review",
            "assignment",
            "assignment_detail",
            "decision",
            "reviewed_by_id",
            "reviewed_at",
            "note",
        )
        read_only_fields = ("id", "reviewed_by_id", "reviewed_at")


class AccessReviewSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = AccessReview
        fields = (
            "id",
            "title",
            "opened_at",
            "closed_at",
            "status",
            "scope_note",
            "item_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "closed_at", "created_at", "updated_at", "version")


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "actor_user_id",
            "actor_username",
            "action",
            "action_display",
            "entity_type",
            "entity_id",
            "entity_label",
            "reason",
            "correlation_id",
            "changes",
            "classification",
            "client_ip",
            "occurred_at",
        )
        read_only_fields = fields
