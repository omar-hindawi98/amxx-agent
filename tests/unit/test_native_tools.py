"""Unit tests for tools/native.py."""

from datetime import UTC, datetime

from amxmodx_genai.tools.native import current_datetime, get_all


def test_current_datetime_is_iso8601():
    result = current_datetime()
    # Must be parseable as ISO 8601 and second-precision (no microseconds).
    parsed = datetime.fromisoformat(result)
    assert parsed.microsecond == 0


def test_current_datetime_is_recent():
    before = datetime.now(UTC).replace(microsecond=0)
    result = current_datetime()
    after = datetime.now(UTC)
    parsed = datetime.fromisoformat(result)
    assert before <= parsed <= after


def test_current_datetime_is_timezone_aware():
    result = current_datetime()
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None


def test_get_all_contains_current_datetime():
    tools = get_all()
    assert current_datetime in tools


def test_get_all_returns_list():
    assert isinstance(get_all(), list)
