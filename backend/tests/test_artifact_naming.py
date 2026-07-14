import re
from datetime import UTC, datetime

import pytest

from backend.app.services.artifact_naming import (
    extraction_run_id,
    filename_timestamp,
    iso_timestamp,
    timestamp_from_iso,
)


@pytest.mark.parametrize(
    ("factory", "value"),
    [
        (iso_timestamp, datetime(2026, 7, 15, 12, 0, 0)),
        (filename_timestamp, datetime(2026, 7, 15, 12, 0, 0)),
        (timestamp_from_iso, "2026-07-15T12:00:00"),
    ],
)
def test_artifact_timestamp_rejects_datetime_without_timezone(factory, value):
    with pytest.raises(ValueError, match="时区"):
        factory(value)


def test_extraction_run_id_uses_timestamp_as_label_not_unique_identity():
    arguments = {
        "doc_id": "apt28_080",
        "model_name": "deepseek-v4-flash",
        "prompt_version": "1.0",
        "generated_at": iso_timestamp(datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)),
    }

    first = extraction_run_id(**arguments)
    second = extraction_run_id(**arguments)

    prefix = "extract-apt28_080-deepseek-v4-flash-1.0-1.0-20260715120000000000-"
    assert first.startswith(prefix)
    assert second.startswith(prefix)
    assert first != second
    assert re.fullmatch(r"extract-[A-Za-z0-9._-]+-\d{20}-[0-9a-f]{8}", first)
