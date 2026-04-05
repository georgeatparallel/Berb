"""Regression tests for BUG-001 (datetime timezone fix).

Test that datetime utilities properly handle UTC timezones.
"""

import pytest
from datetime import datetime, timezone, timedelta
from berb.utils.time import (
    utcnow,
    utcnow_iso,
    utc_timestamp,
    utcnow_str,
    ensure_utc,
    duration_seconds,
)


class TestUTCTimeUtilities:
    """Test UTC time utility functions."""

    def test_utcnow_returns_aware_datetime(self):
        """BUG-001 REGRESSION: utcnow() must return timezone-aware datetime."""
        result = utcnow()
        
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

    def test_utcnow_always_utc(self):
        """Verify utcnow() always returns UTC regardless of system timezone."""
        result = utcnow()
        
        # UTC offset should be 0
        assert result.utcoffset() == timedelta(0)

    def test_utcnow_iso_format(self):
        """Test utcnow_iso() returns proper ISO format with timezone."""
        result = utcnow_iso()
        
        # Should be ISO 8601 format with timezone
        assert "+00:00" in result or "Z" in result or result.endswith("+0000")
        
        # Should parse back to a valid datetime
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_utcnow_iso_custom_timespec(self):
        """Test utcnow_iso() with custom timespec."""
        result = utcnow_iso(timespec="milliseconds")
        
        # Should have millisecond precision
        assert "." in result

    def test_utc_timestamp_returns_float(self):
        """Test utc_timestamp() returns float."""
        result = utc_timestamp()
        
        assert isinstance(result, float)
        assert result > 0
        
        # Should be reasonable (after year 2000)
        assert result > 946684800.0  # 2000-01-01 00:00:00 UTC

    def test_utcnow_str_format(self):
        """Test utcnow_str() with custom format."""
        result = utcnow_str("%Y-%m-%d")
        
        # Should match current UTC date
        expected = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert result == expected

    def test_ensure_utc_naive_datetime(self):
        """Test ensure_utc() with naive datetime assumes UTC."""
        naive = datetime(2026, 3, 29, 12, 0, 0)
        result = ensure_utc(naive)
        
        assert result.tzinfo == timezone.utc
        assert result.hour == 12  # Same hour, just made aware

    def test_ensure_utc_aware_datetime(self):
        """Test ensure_utc() converts aware datetime to UTC."""
        # Create datetime in different timezone (UTC+5)
        tz_plus5 = timezone(timedelta(hours=5))
        aware = datetime(2026, 3, 29, 12, 0, 0, tzinfo=tz_plus5)
        
        result = ensure_utc(aware)
        
        assert result.tzinfo == timezone.utc
        assert result.hour == 7  # 12:00 UTC+5 = 07:00 UTC

    def test_ensure_utc_invalid_type(self):
        """Test ensure_utc() raises on invalid type."""
        with pytest.raises(TypeError):
            ensure_utc("not a datetime")  # type: ignore

    def test_duration_seconds(self):
        """Test duration_seconds() calculates correctly."""
        import time
        
        start = utcnow()
        time.sleep(0.1)
        elapsed = duration_seconds(start)
        
        assert elapsed >= 0.1
        assert elapsed < 1.0  # Should be reasonably close

    def test_duration_seconds_with_end(self):
        """Test duration_seconds() with explicit end time."""
        start = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 29, 12, 1, 0, tzinfo=timezone.utc)
        
        elapsed = duration_seconds(start, end)
        
        assert elapsed == 60.0

    def test_duration_seconds_mixed_timezones(self):
        """Test duration_seconds() handles mixed timezones correctly."""
        # Start in UTC
        start = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)
        
        # End in UTC+2
        tz_plus2 = timezone(timedelta(hours=2))
        end = datetime(2026, 3, 29, 14, 0, 0, tzinfo=tz_plus2)  # Same instant as 12:00 UTC
        
        elapsed = duration_seconds(start, end)
        
        # Should be 0 (same instant in time)
        assert abs(elapsed) < 0.001


class TestDatetimeConsistency:
    """Test datetime consistency across Berb modules."""

    def test_self_correcting_uses_utc(self):
        """BUG-001: Verify self_correcting.py uses UTC timestamps."""
        # Import here to check the module
        from berb.experiment.self_correcting import SelfCorrectingExecutor
        from berb.utils.time import utc_timestamp
        
        # The module should import utc_timestamp
        # This is a compile-time check - if the import fails, the fix wasn't applied
        import inspect
        source = inspect.getsource(SelfCorrectingExecutor)
        
        # Should use utc_timestamp, not datetime.now().timestamp()
        assert "utc_timestamp()" in source or "from berb.utils.time import" in source

    def test_timestamp_uniqueness(self):
        """Test that UTC timestamps are unique across rapid calls."""
        timestamps = [utc_timestamp() for _ in range(100)]
        
        # All timestamps should be unique (or very close)
        unique = set(timestamps)
        
        # With microsecond precision, we expect high uniqueness
        # Allow for some collisions due to CPU speed
        assert len(unique) >= len(timestamps) * 0.9

    def test_serialization_compatibility(self):
        """Test that UTC datetimes serialize/deserialize correctly."""
        import json
        
        dt = utcnow()
        iso_str = dt.isoformat()
        
        # Serialize and deserialize
        restored = datetime.fromisoformat(iso_str)
        
        assert restored.tzinfo is not None
        assert restored.utcoffset() == timedelta(0)
