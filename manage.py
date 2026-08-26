#!/usr/bin/env python
"""ابزار خط فرمان مدیریت پروژه Django."""
import os
import sys


def _force_utf8_output() -> None:
    """
    خروجی کنسول را UTF-8 می‌کند.

    کنسول پیش‌فرض ویندوز (cp1252/cp1256) نمی‌تواند متن فارسی را چاپ کند و
    دستورات مدیریتی با UnicodeEncodeError شکست می‌خورند.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover
                pass


def main() -> None:
    _force_utf8_output()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django نصب نیست. محیط مجازی را فعال کنید و requirements.txt را نصب کنید."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
