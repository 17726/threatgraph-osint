"""项目统一使用的 JSON Schema 格式校验器。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from jsonschema import FormatChecker


_RFC3339_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _is_aware_rfc3339_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not _RFC3339_DATETIME_PATTERN.fullmatch(value):
        return False
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment.tzinfo is not None and moment.utcoffset() is not None


STRICT_FORMAT_CHECKER = FormatChecker()
STRICT_FORMAT_CHECKER.checks("date-time", raises=(TypeError, ValueError))(
    _is_aware_rfc3339_datetime
)
