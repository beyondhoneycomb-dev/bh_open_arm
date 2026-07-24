"""WP-3D-06 ② — gain-profile tagging and merge-time verification.

`FR-DAT-045` / `02b` §8.2 WP-3D-06 ②: a dataset is tagged with its follower PD gain
profile; a merge verifies the tags agree; a gain-tagless source is FAIL_BLOCKING. Because
gain — not the profile name — drives the following-error distribution, equality is on the
kp/kd vectors, so two datasets both tagged `custom` with different gains do not match.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.dataset.merge.gain import (
    GainProfile,
    GainProfileError,
    GainProfileMismatchError,
    GainTagMissingError,
    read_gain_profile,
    verify_uniform_gain,
    write_gain_profile,
)

_COMPLIANT = GainProfile(
    profile_id="compliant",
    kp=(70.0, 70.0, 70.0, 60.0, 10.0, 10.0, 10.0, 10.0),
    kd=(2.75, 2.5, 2.0, 2.0, 0.7, 0.6, 0.5, 0.2),
)
_STIFF = GainProfile(
    profile_id="stiff",
    kp=(230.0, 230.0, 190.0, 190.0, 30.0, 30.0, 30.0, 10.0),
    kd=(2.7, 2.7, 2.2, 2.2, 1.5, 1.5, 1.5, 0.2),
)


def test_out_of_band_gain_refused() -> None:
    """A kp above the DM MIT band never came from a real profile and is refused."""
    with pytest.raises(GainProfileError, match="kp"):
        GainProfile(profile_id="custom", kp=(600.0,), kd=(1.0,))


def test_kp_kd_width_mismatch_refused() -> None:
    """A kp/kd width mismatch is refused at construction."""
    with pytest.raises(GainProfileError, match="width"):
        GainProfile(profile_id="custom", kp=(10.0, 10.0), kd=(1.0,))


def test_uniform_gain_accepted() -> None:
    """Identical profiles pass and the shared profile is returned."""
    shared = verify_uniform_gain([_COMPLIANT, _COMPLIANT])
    assert shared.profile_id == "compliant"


def test_different_profiles_blocked() -> None:
    """Two different gain profiles refuse the merge (distribution would split)."""
    with pytest.raises(GainProfileMismatchError, match="following-error distribution"):
        verify_uniform_gain([_COMPLIANT, _STIFF])


def test_same_id_different_gains_blocked() -> None:
    """Two 'custom' tags with different kp are distinct distributions, so blocked."""
    a = GainProfile(profile_id="custom", kp=(100.0,), kd=(1.0,))
    b = GainProfile(profile_id="custom", kp=(120.0,), kd=(1.0,))
    with pytest.raises(GainProfileMismatchError):
        verify_uniform_gain([a, b])


def test_tag_round_trips(tmp_path: Path) -> None:
    """A written tag reads back identical."""
    write_gain_profile(tmp_path, _STIFF)
    assert read_gain_profile("synthetic/x", tmp_path) == _STIFF


def test_missing_tag_is_fail_blocking(tmp_path: Path) -> None:
    """A dataset with no gain tag raises the FAIL_BLOCKING error."""
    with pytest.raises(GainTagMissingError, match="FAIL_BLOCKING"):
        read_gain_profile("synthetic/untagged", tmp_path)
