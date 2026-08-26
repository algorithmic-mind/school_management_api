"""
مدل‌های هویت، دسترسی و ممیزی.

مرجع: بخش ۷.۲ (هویت) و ۷.۳ (نقش، مجوز و ممیزی دسترسی) سند تحلیل.

نکته طراحی کلیدی (بخش ۱): یک «شخص» می‌تواند هم‌زمان چند نقش داشته باشد؛
بنابراین Person از Student/Guardian/Employee و از UserAccount جدا است.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import (
    AddressType,
    ContactType,
    DataClassification,
    Gender,
    VerificationStatus,
)
from apps.core.models import (
    BaseTenantModel,
    EffectiveDatedModel,
    Tenant,
    UUIDModel,
)
from apps.core.permissions import ScopeType
from apps.identity.enums import (
    AccessReviewDecision,
    AccessReviewStatus,
    AuditAction,
    MfaMethod,
    PersonStatus,
    RoleAssignmentStatus,
    UserStatus,
)


class Person(BaseTenantModel):
    """
    هویت پایه فرد؛ مستقل از نقش دانش‌آموز، ولی یا کارمند (بخش ۵ واژگان).
    """

    national_id = models.CharField(
        max_length=20, blank=True, db_index=True, verbose_name=_("شماره ملی")
    )
    passport_no = models.CharField(
        max_length=30, blank=True, verbose_name=_("شماره گذرنامه")
    )
    first_name = models.CharField(max_length=100, verbose_name=_("نام"))
    last_name = models.CharField(max_length=150, verbose_name=_("نام خانوادگی"))
    father_name = models.CharField(
        max_length=100, blank=True, verbose_name=_("نام پدر")
    )
    birth_date = models.DateField(
        null=True, blank=True, verbose_name=_("تاریخ تولد")
    )
    birth_place = models.CharField(
        max_length=120, blank=True, verbose_name=_("محل تولد")
    )
    gender = models.CharField(
        max_length=15,
        choices=Gender.choices,
        default=Gender.UNDISCLOSED,
        verbose_name=_("جنسیت"),
    )
    nationality = models.CharField(
        max_length=60, blank=True, verbose_name=_("تابعیت")
    )
    preferred_language = models.CharField(
        max_length=10, default="fa", verbose_name=_("زبان ترجیحی")
    )
    photo = models.ImageField(
        upload_to="persons/", null=True, blank=True, verbose_name=_("تصویر")
    )
    accessibility_needs = models.TextField(
        blank=True, verbose_name=_("نیازهای دسترس‌پذیری")
    )
    status = models.CharField(
        max_length=20, choices=PersonStatus.choices, default=PersonStatus.ACTIVE
    )
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_from",
        verbose_name=_("ادغام‌شده در"),
    )

    class Meta:
        verbose_name = _("شخص")
        verbose_name_plural = _("اشخاص")
        ordering = ("last_name", "first_name")
        constraints = [
            # شناسه ملی پس از نرمال‌سازی در سطح Tenant یکتا است (بخش ۷.۲)
            models.UniqueConstraint(
                fields=["tenant", "national_id"],
                condition=~models.Q(national_id=""),
                name="uq_person_tenant_national_id",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "last_name", "first_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class ContactPoint(BaseTenantModel):
    """راه‌های تماس شخص."""

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="contact_points"
    )
    contact_type = models.CharField(
        max_length=20, choices=ContactType.choices, verbose_name=_("نوع تماس")
    )
    value = models.CharField(max_length=200, verbose_name=_("مقدار"))
    is_primary = models.BooleanField(default=False, verbose_name=_("تماس اصلی"))
    is_verified = models.BooleanField(default=False, verbose_name=_("تأییدشده"))
    verified_at = models.DateTimeField(null=True, blank=True)
    label = models.CharField(max_length=60, blank=True, verbose_name=_("برچسب"))

    class Meta:
        verbose_name = _("راه تماس")
        verbose_name_plural = _("راه‌های تماس")
        ordering = ("-is_primary", "contact_type")
        indexes = [models.Index(fields=["person", "contact_type"])]

    def __str__(self) -> str:
        return f"{self.get_contact_type_display()}: {self.value}"


class Address(BaseTenantModel):
    """نشانی — به‌صورت مستقل نگهداری می‌شود تا خانواده بتواند آن را به اشتراک بگذارد."""

    country = models.CharField(max_length=60, default="ایران")
    province = models.CharField(max_length=80, blank=True, verbose_name=_("استان"))
    city = models.CharField(max_length=80, blank=True, verbose_name=_("شهر"))
    district = models.CharField(max_length=80, blank=True, verbose_name=_("منطقه"))
    postal_code = models.CharField(max_length=20, blank=True, verbose_name=_("کد پستی"))
    line = models.CharField(max_length=400, verbose_name=_("نشانی"))
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    class Meta:
        verbose_name = _("نشانی")
        verbose_name_plural = _("نشانی‌ها")

    def __str__(self) -> str:
        return f"{self.city} - {self.line[:50]}"


class PersonAddress(BaseTenantModel, EffectiveDatedModel):
    """انتساب زمان‌مند نشانی به شخص."""

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="person_addresses"
    )
    address = models.ForeignKey(
        Address, on_delete=models.PROTECT, related_name="person_links"
    )
    address_type = models.CharField(
        max_length=20, choices=AddressType.choices, default=AddressType.HOME
    )

    class Meta:
        verbose_name = _("نشانی شخص")
        verbose_name_plural = _("نشانی‌های اشخاص")
        ordering = ("-effective_from",)


class UserAccountManager(BaseUserManager):
    """مدیریت ساخت حساب کاربری."""

    use_in_migrations = True

    def _create_user(self, username: str, password: str | None, **extra):
        if not username:
            raise ValueError("نام کاربری الزامی است.")
        user = self.model(username=username, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username: str, password: str | None = None, **extra):
        extra.setdefault("status", UserStatus.ACTIVE)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(username, password, **extra)

    def create_superuser(self, username: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("status", UserStatus.ACTIVE)
        if extra.get("is_superuser") is not True:
            raise ValueError("کاربر ارشد باید is_superuser=True داشته باشد.")
        return self._create_user(username, password, **extra)


class UserAccount(UUIDModel, AbstractBaseUser, PermissionsMixin):
    """
    حساب کاربری — معادل USER_ACCOUNT در بخش ۷.۲ و ۷.۳.

    از Person جدا است: یک شخص می‌تواند حساب نداشته باشد (مثلاً دانش‌آموز کم‌سن)
    یا حسابش بعداً ساخته شود.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="users", null=True, blank=True
    )
    person = models.OneToOneField(
        Person,
        on_delete=models.PROTECT,
        related_name="user_account",
        null=True,
        blank=True,
        verbose_name=_("شخص"),
    )
    username = models.CharField(
        max_length=150, unique=True, db_index=True, verbose_name=_("نام کاربری")
    )
    email = models.EmailField(blank=True, verbose_name=_("ایمیل"))
    mobile = models.CharField(
        max_length=20, blank=True, db_index=True, verbose_name=_("تلفن همراه")
    )
    status = models.CharField(
        max_length=20,
        choices=UserStatus.choices,
        default=UserStatus.INVITED,
        verbose_name=_("وضعیت حساب"),
    )
    mfa_enabled = models.BooleanField(
        default=False, verbose_name=_("احراز هویت دومرحله‌ای")
    )
    mfa_method = models.CharField(
        max_length=15, choices=MfaMethod.choices, default=MfaMethod.NONE
    )
    must_change_password = models.BooleanField(default=False)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    failed_login_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    is_staff = models.BooleanField(default=False, verbose_name=_("دسترسی پنل مدیریت"))
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserAccountManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("حساب کاربری")
        verbose_name_plural = _("حساب‌های کاربری")
        ordering = ("username",)

    def __str__(self) -> str:
        return self.username

    @property
    def display_name(self) -> str:
        if self.person_id:
            return self.person.full_name
        return self.username

    # -- RBAC -----------------------------------------------------------
    def active_assignments(self):
        today = timezone.localdate()
        return self.role_assignments.filter(
            status=RoleAssignmentStatus.ACTIVE, effective_from__lte=today
        ).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=today))

    def get_effective_permission_codes(self) -> set[str]:
        """
        مجموعه کدهای مجوز مؤثر کاربر.

        بخش ۷.۳: «انتساب‌های منقضی به‌طور خودکار از تصمیم مجوز خارج می‌شوند.»
        """
        if self.is_superuser:
            return {"*"}
        return set(
            Permission.objects.filter(
                role_links__role__user_assignments__in=self.active_assignments()
            )
            .values_list("code", flat=True)
            .distinct()
        )

    def get_effective_scopes(self) -> list[dict]:
        return list(
            self.active_assignments()
            .select_related("role")
            .values("role__code", "role__title", "scope_type", "scope_id")
        )

    def has_perm_code(self, code: str) -> bool:
        if self.is_superuser:
            return True
        return code in self.get_effective_permission_codes()


class Permission(UUIDModel):
    """
    مجوز اتمی: عمل دقیق روی منبع، مانند `student.read` (بخش ۳.۲).

    این مدل مستقل از سیستم مجوز داخلی Django است و کدهای دامنه‌ای را نگه می‌دارد.
    """

    code = models.CharField(
        max_length=100, unique=True, db_index=True, verbose_name=_("کد مجوز")
    )
    resource = models.CharField(max_length=60, db_index=True, verbose_name=_("منبع"))
    action = models.CharField(max_length=40, verbose_name=_("عمل"))
    title = models.CharField(max_length=150, verbose_name=_("عنوان فارسی"))
    module = models.CharField(max_length=40, blank=True, verbose_name=_("ماژول"))
    description = models.CharField(max_length=300, blank=True)
    is_sensitive = models.BooleanField(
        default=False, verbose_name=_("حساس (نیازمند بازبینی دوره‌ای)")
    )

    class Meta:
        verbose_name = _("مجوز")
        verbose_name_plural = _("مجوزها")
        ordering = ("module", "resource", "action")

    def __str__(self) -> str:
        return self.code


class Role(BaseTenantModel):
    """نقش: مجموعه‌ای از مجوزها (بخش ۳.۲)."""

    code = models.CharField(max_length=60, db_index=True, verbose_name=_("کد نقش"))
    title = models.CharField(max_length=150, verbose_name=_("عنوان نقش"))
    description = models.CharField(max_length=400, blank=True)
    is_system = models.BooleanField(
        default=False, verbose_name=_("نقش سیستمی (غیرقابل حذف)")
    )
    requires_mfa = models.BooleanField(
        default=False, verbose_name=_("نیازمند احراز دومرحله‌ای")
    )
    allowed_scope_types = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("انواع Scope مجاز"),
        help_text=_("مثلاً [\"SCHOOL\", \"CAMPUS\"]"),
    )
    permissions = models.ManyToManyField(
        Permission, through="RolePermission", related_name="roles"
    )

    class Meta:
        verbose_name = _("نقش")
        verbose_name_plural = _("نقش‌ها")
        ordering = ("title",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uq_role_tenant_code"
            )
        ]

    def __str__(self) -> str:
        return self.title


class RolePermission(UUIDModel):
    """جدول واسط نقش و مجوز."""

    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="permission_links"
    )
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="role_links"
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("مجوز نقش")
        verbose_name_plural = _("مجوزهای نقش")
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"], name="uq_role_permission"
            )
        ]


class UserRoleAssignment(BaseTenantModel, EffectiveDatedModel):
    """
    انتساب نقش به کاربر در یک دامنه مشخص.

    بخش ۷.۳: «scope_type + scope_id باید به محدوده مجاز نقش اشاره کند؛
    ارجاع چندریختی در لایه برنامه اعتبارسنجی می‌شود.»
    """

    user = models.ForeignKey(
        UserAccount, on_delete=models.CASCADE, related_name="role_assignments"
    )
    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, related_name="user_assignments"
    )
    scope_type = models.CharField(
        max_length=25,
        choices=ScopeType.CHOICES,
        default=ScopeType.SCHOOL,
        verbose_name=_("نوع دامنه"),
    )
    scope_id = models.UUIDField(
        null=True, blank=True, db_index=True, verbose_name=_("شناسه دامنه")
    )
    status = models.CharField(
        max_length=20,
        choices=RoleAssignmentStatus.choices,
        default=RoleAssignmentStatus.ACTIVE,
    )
    granted_by_id = models.UUIDField(null=True, blank=True)
    grant_reason = models.CharField(max_length=300, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("انتساب نقش")
        verbose_name_plural = _("انتساب‌های نقش")
        ordering = ("-effective_from",)
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["scope_type", "scope_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.role} ({self.scope_type})"


class AccessReview(BaseTenantModel):
    """
    دوره بازبینی دسترسی.

    بخش ۷.۳: «دسترسی نقش‌های حساس حداقل هر فصل بازبینی می‌شود.»
    """

    title = models.CharField(max_length=200, verbose_name=_("عنوان دوره بازبینی"))
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=AccessReviewStatus.choices,
        default=AccessReviewStatus.OPEN,
    )
    scope_note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("بازبینی دسترسی")
        verbose_name_plural = _("بازبینی‌های دسترسی")
        ordering = ("-opened_at",)

    def __str__(self) -> str:
        return self.title


class AccessReviewItem(BaseTenantModel):
    """قلم بازبینی: تصمیم درباره یک انتساب نقش."""

    review = models.ForeignKey(
        AccessReview, on_delete=models.CASCADE, related_name="items"
    )
    assignment = models.ForeignKey(
        UserRoleAssignment, on_delete=models.CASCADE, related_name="review_items"
    )
    decision = models.CharField(
        max_length=20,
        choices=AccessReviewDecision.choices,
        default=AccessReviewDecision.PENDING,
    )
    reviewed_by_id = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("قلم بازبینی دسترسی")
        verbose_name_plural = _("اقلام بازبینی دسترسی")
        constraints = [
            models.UniqueConstraint(
                fields=["review", "assignment"], name="uq_review_assignment"
            )
        ]


class AuditLog(UUIDModel):
    """
    گزارش ممیزی — فقط Append.

    بخش ۷.۳: «ممیزی فقط Append است و داده قبل/بعد برای فیلدهای مجاز به‌صورت
    Snapshot یا Diff نگهداری می‌شود؛ مقادیر راز مانند رمز عبور هرگز ثبت
    نمی‌شوند.»
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="audit_logs", null=True
    )
    actor_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_username = models.CharField(max_length=150, blank=True)
    action = models.CharField(
        max_length=30, choices=AuditAction.choices, db_index=True
    )
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.UUIDField(null=True, blank=True, db_index=True)
    entity_label = models.CharField(max_length=250, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    changes = models.JSONField(
        default=dict, blank=True, verbose_name=_("تغییرات (Diff)")
    )
    classification = models.CharField(
        max_length=20,
        choices=DataClassification.choices,
        default=DataClassification.INTERNAL,
    )
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _("رکورد ممیزی")
        verbose_name_plural = _("گزارش ممیزی")
        ordering = ("-occurred_at",)
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["tenant", "-occurred_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type} @ {self.occurred_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("رکورد ممیزی تغییرناپذیر است.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError("رکورد ممیزی حذف نمی‌شود.")


class PersonDocument(BaseTenantModel):
    """مدارک شخص (بخش ۷.۲ — DOCUMENT / PERSON_DOCUMENT)."""

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="documents"
    )
    document_type = models.CharField(max_length=60, verbose_name=_("نوع مدرک"))
    title = models.CharField(max_length=200, blank=True)
    file = models.FileField(upload_to="person-documents/", verbose_name=_("فایل"))
    sha256 = models.CharField(max_length=64, blank=True, verbose_name=_("هش فایل"))
    classification = models.CharField(
        max_length=20,
        choices=DataClassification.choices,
        default=DataClassification.CONFIDENTIAL,
    )
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    verified_by_id = models.UUIDField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    purpose = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = _("مدرک شخص")
        verbose_name_plural = _("مدارک اشخاص")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["person", "document_type"])]

    def __str__(self) -> str:
        return f"{self.document_type} — {self.person}"
