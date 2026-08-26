"""سریالایزرهای مشترک و مستندسازی قالب خطا در OpenAPI."""

from rest_framework import serializers


class FieldErrorSerializer(serializers.Serializer):
    """یک خطای فیلدی در قالب پاسخ خطا (بخش ۱۲.۳)."""

    field = serializers.CharField(help_text="نام فیلد دارای خطا، مثلاً `classGroupId`")
    reason = serializers.CharField(help_text="علت خطا به‌صورت کد یا متن کوتاه")


class ErrorResponseSerializer(serializers.Serializer):
    """قالب استاندارد خطای همه Endpointها."""

    code = serializers.CharField(
        help_text="کد معنایی خطا؛ فرانت باید روی این مقدار تصمیم بگیرد نه روی متن پیام."
    )
    message = serializers.CharField(help_text="پیام قابل نمایش به کاربر (فارسی)")
    correlationId = serializers.CharField(
        help_text="شناسه ردیابی درخواست؛ در گزارش خطا به پشتیبانی ارسال شود."
    )
    fieldErrors = FieldErrorSerializer(many=True, required=False)
    retryable = serializers.BooleanField(
        help_text="آیا تکرار همان درخواست می‌تواند موفق شود؟"
    )


class BaseModelSerializer(serializers.ModelSerializer):
    """
    سریالایزر پایه با فیلدهای ممیزی فقط‌خواندنی.

    `version` برای هدر `If-Match` استفاده می‌شود.
    """

    class Meta:
        abstract = True
        read_only_fields = (
            "id",
            "created_at",
            "created_by_id",
            "updated_at",
            "updated_by_id",
            "version",
        )


AUDIT_FIELDS = ("id", "created_at", "updated_at", "version")


class ReasonSerializer(serializers.Serializer):
    """بدنه عملیاتی که نیازمند ثبت علت است (لغو، ابطال، بازگشایی)."""

    reason = serializers.CharField(
        max_length=500, help_text="علت انجام عملیات؛ در ممیزی ثبت می‌شود."
    )


class ApprovalDecisionSerializer(serializers.Serializer):
    """بدنه تصمیم تأیید یا رد."""

    comment = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, help_text="توضیح تصمیم"
    )


class BulkIdsSerializer(serializers.Serializer):
    """عملیات گروهی روی مجموعه‌ای از شناسه‌ها."""

    ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False, max_length=1000
    )


class OperationResultSerializer(serializers.Serializer):
    """پاسخ عمومی عملیات فرمانی."""

    success = serializers.BooleanField()
    message = serializers.CharField(required=False, allow_blank=True)
    affected = serializers.IntegerField(required=False)


class MoneySerializer(serializers.Serializer):
    """
    مبلغ با واحد پول.

    مبالغ به‌صورت عدد صحیح در کوچک‌ترین واحد پولی ذخیره می‌شوند
    (بخش ۱ سند تحلیل: محاسبات مالی از نوع اعشاری شناور نیستند).
    """

    amount = serializers.IntegerField(help_text="مبلغ به کوچک‌ترین واحد پولی (ریال)")
    currency = serializers.CharField(max_length=3, default="IRR")
