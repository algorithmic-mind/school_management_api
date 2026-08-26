from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "زیرساخت مشترک"

    def ready(self):
        """
        برچسب فارسی فیلدهایی که در `models.py` صریح تعریف نشده‌اند.

        اینجا اجرا می‌شود چون در این مرحله همه مدل‌ها بارگذاری شده‌اند اما هنوز
        نه فرمی ساخته شده، نه سریالایزری و نه Schemaیی — پس هر سه مصرف‌کننده
        برچسب درست را می‌بینند.
        """
        from apps.core.field_labels import apply_field_labels

        apply_field_labels()
