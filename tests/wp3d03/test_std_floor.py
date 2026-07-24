"""WP-3D-03 ③ — a stuck channel (std close to zero) is detected and warned.

`02b` §8.2 WP-3D-03 ③: a stationary `.vel` or a non-contact `.torque` has std about
zero and explodes MEAN_STD/MIN_MAX normalization, so those channels must be detected
and warned. The synthetic robot never loads a joint, so every `.torque` channel is
naturally stationary — the exact non-contact case the plan names.
"""

from __future__ import annotations

import logging

import backend.dataset.stats as stats
from contracts.recorder import TORQUE_SUFFIX
from tests.wp3d03 import support

_FLOOR = 1e-3


def test_non_contact_torque_channels_are_flagged() -> None:
    """The fixture's non-contact `.torque` channels fall below the floor and are flagged."""
    feats = support.features()
    result = stats.fit_normalization_stats(support.episode_generator(3), feats)

    report = stats.detect_std_floor_violations(result, support.names(), floor=_FLOOR)

    assert not report.ok
    flagged_suffixes = {violation.suffix for violation in report.violations}
    assert TORQUE_SUFFIX in flagged_suffixes
    for violation in report.violations:
        assert violation.std < _FLOOR
        assert violation.channel_name.endswith(violation.suffix or "")


def test_violation_is_warned() -> None:
    """Each flagged channel emits a warning, so a stuck channel is visible in the log."""
    feats = support.features()
    result = stats.fit_normalization_stats(support.episode_generator(2), feats)

    with_warnings = logging.getLogger("backend.dataset.stats.stdfloor")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    with_warnings.addHandler(handler)
    try:
        report = stats.detect_std_floor_violations(result, support.names(), floor=_FLOOR)
    finally:
        with_warnings.removeHandler(handler)

    assert len(records) == len(report.violations)
    assert all(record.levelno == logging.WARNING for record in records)


def test_floor_of_zero_flags_nothing_without_a_stuck_channel() -> None:
    """A floor of zero flags no channel — the detection respects the supplied bar."""
    feats = support.features()
    result = stats.fit_normalization_stats(support.episode_generator(3), feats)

    report = stats.detect_std_floor_violations(result, support.names(), floor=0.0)

    assert report.ok
    assert report.violations == ()
