"""فیلتر Log برای افزودن correlation_id به هر رکورد."""

import logging

from apps.core.context import get_correlation_id


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True
