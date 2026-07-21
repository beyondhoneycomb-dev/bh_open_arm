"""The four-parameter load profile records all four params and rejects nonsense.

Acceptance ② rests on the profile: it must record exactly the four canonical
parameters, and a run that fails to record them all must be refusable. This suite
covers the profile's own guarantees; the artifact-level refusal is in
`test_artifact_refusal`.
"""

from __future__ import annotations

import pytest

from sim.harness.load_profile import (
    REQUIRED_PARAM_KEYS,
    InvalidLoadProfileError,
    LoadProfile,
    profile_is_fully_recorded,
)


def test_as_record_carries_all_four_parameters() -> None:
    """The record has exactly the four canonical keys, resolution as a pair."""
    profile = LoadProfile(5, 640, 480, 48 * 1024, 256 * 1024)
    record = profile.as_record()
    assert set(record) == set(REQUIRED_PARAM_KEYS)
    assert record["stream_count"] == 5
    assert record["resolution"] == [640, 480]
    assert record["png_write_bytes_per_frame"] == 48 * 1024
    assert record["serialize_bytes_per_tick"] == 256 * 1024


def test_fully_recorded_predicate() -> None:
    """A complete record is recorded; a missing key or None value is not."""
    complete = LoadProfile(5, 640, 480, 1024, 2048).as_record()
    assert profile_is_fully_recorded(complete)
    assert not profile_is_fully_recorded(None)
    assert not profile_is_fully_recorded({})

    missing = dict(complete)
    del missing["serialize_bytes_per_tick"]
    assert not profile_is_fully_recorded(missing)

    nulled = dict(complete)
    nulled["png_write_bytes_per_frame"] = None
    assert not profile_is_fully_recorded(nulled)


def test_negative_parameter_is_rejected() -> None:
    """A negative parameter cannot describe a real load and is refused at construction."""
    with pytest.raises(InvalidLoadProfileError):
        LoadProfile(-1, 640, 480, 1024, 2048)
    with pytest.raises(InvalidLoadProfileError):
        LoadProfile(5, 640, 480, -1, 2048)


def test_no_load_predicate() -> None:
    """A zero-stream or zero-bytes profile is no-load; a real one is not."""
    assert LoadProfile(0, 640, 480, 1024, 2048).is_no_load
    assert LoadProfile(5, 640, 480, 0, 0).is_no_load
    assert not LoadProfile(5, 640, 480, 1024, 0).is_no_load
    assert not LoadProfile(5, 320, 240, 1024, 2048).is_no_load


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
