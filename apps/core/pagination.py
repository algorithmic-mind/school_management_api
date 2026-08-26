"""
صفحه‌بندی.

بخش ۱۲.۴: «Pagination ترجیحاً Cursor-based است؛ Export بزرگ از مسیر Job.»
برای فهرست‌های مدیریتی که نیاز به شماره صفحه و تعداد کل دارند، صفحه‌بندی
شماره‌ای پیش‌فرض است و Cursor برای جریان‌های پرتغییر (Feed، Log، Audit).
"""

from collections import OrderedDict

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class DefaultPageNumberPagination(PageNumberPagination):
    """صفحه‌بندی شماره‌ای با پاکت یکسان برای همه فهرست‌ها."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200
    page_query_param = "page"

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("pageCount", self.page.paginator.num_pages),
                    ("page", self.page.number),
                    ("pageSize", self.get_page_size(self.request)),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "required": ["count", "results"],
            "properties": {
                "count": {"type": "integer", "example": 137, "description": "تعداد کل رکوردها"},
                "pageCount": {"type": "integer", "example": 6, "description": "تعداد صفحات"},
                "page": {"type": "integer", "example": 1, "description": "شماره صفحه جاری"},
                "pageSize": {"type": "integer", "example": 25, "description": "اندازه صفحه"},
                "next": {"type": "string", "nullable": True, "format": "uri"},
                "previous": {"type": "string", "nullable": True, "format": "uri"},
                "results": schema,
            },
        }


class TimelineCursorPagination(CursorPagination):
    """
    صفحه‌بندی Cursor برای داده‌های زمانی و پرتغییر:
    ممیزی، اعلان، حرکت موجودی، رخداد آزمون.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = "-created_at"
    cursor_query_param = "cursor"

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("pageSize", self.get_page_size(self.request)),
                    ("results", data),
                ]
            )
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "required": ["results"],
            "properties": {
                "next": {"type": "string", "nullable": True, "format": "uri"},
                "previous": {"type": "string", "nullable": True, "format": "uri"},
                "pageSize": {"type": "integer", "example": 50},
                "results": schema,
            },
        }


class AuditCursorPagination(TimelineCursorPagination):
    ordering = "-occurred_at"
