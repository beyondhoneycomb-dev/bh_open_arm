"""Each of the four capture-preservation checks bites on its injected mismatch.

For every fault the matching check must FAIL while the other three PASS (the
injectors are surgical), the delete must be REFUSED, the raw source must be left
intact, and the offending episode must be flagged. A check that failed to bite here
would license an irreversible delete of a source the conversion did not preserve
(`02b` §7.2 WP-3C-06 ⑤, the `FAIL_BLOCKING` branch).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.capture_interlock import (
    CHECK_CAPTURE_TS,
    CHECK_FRAME_COUNT,
    CHECK_ROW_COUNT,
    CHECK_VIDEO_LENGTH,
    REQUIRED_CAPTURE_CHECKS,
    VERDICT_REFUSED,
    CaptureSource,
    SourceDeleteInterlock,
)
from backend.capture_interlock.constants import FLAG_SIDECAR_TEMPLATE
from tests.wp3c06 import faults
from tests.wp3c06.materialize import Fixture

# Each fault, the check it must trip, and the episode it targets. All four target
# episode 0, so the untouched episode 1 stays PRESERVED — proving the mismatch is
# isolated to the corrupted episode, not smeared across the dataset.
_FAULTS: list[tuple[str, Callable[[Fixture], None], str]] = [
    (CHECK_FRAME_COUNT, faults.inject_frame_count_short, "frame count short"),
    (CHECK_VIDEO_LENGTH, faults.inject_video_length_off, "video length off"),
    (CHECK_ROW_COUNT, faults.inject_row_count_off, "row count off"),
    (CHECK_CAPTURE_TS, faults.inject_capture_ts_reordered, "capture_ts reordered"),
]

_TARGET_EPISODE = 0


@pytest.mark.parametrize(
    ("expected_check", "inject", "label"),
    _FAULTS,
    ids=[label for _, _, label in _FAULTS],
)
def test_injected_mismatch_bites_and_refuses_delete(
    pair: Fixture,
    expected_check: str,
    inject: Callable[[Fixture], None],
    label: str,
) -> None:
    """The matching check fails, others pass, delete is refused, raw is intact + flagged."""
    inject(pair)

    interlock = SourceDeleteInterlock()
    decision = interlock.decide(pair.raw_root, pair.converted_root)

    # The delete is refused and the targeted episode is a MISMATCH.
    assert not decision.deletable
    assert decision.verdict == VERDICT_REFUSED
    assert _TARGET_EPISODE in decision.flagged_episodes

    target = next(ep for ep in decision.episodes if ep.episode_index == _TARGET_EPISODE)
    assert not target.preserved

    # The matching check bit; the other three did not (the injector is surgical).
    failed_check = target.result(expected_check)
    assert failed_check is not None and not failed_check.passed, label
    for other in REQUIRED_CAPTURE_CHECKS:
        if other == expected_check:
            continue
        result = target.result(other)
        assert result is not None and result.passed, f"{other} should still pass after {label}"

    # The untouched episode stays PRESERVED.
    untouched = next(ep for ep in decision.episodes if ep.episode_index != _TARGET_EPISODE)
    assert untouched.preserved, untouched.reasons()


@pytest.mark.parametrize(
    ("expected_check", "inject", "label"),
    _FAULTS,
    ids=[label for _, _, label in _FAULTS],
)
def test_refused_delete_preserves_source_and_writes_flag(
    pair: Fixture,
    expected_check: str,
    inject: Callable[[Fixture], None],
    label: str,
) -> None:
    """delete_if_certified never deletes on a mismatch; the raw source and a flag remain."""
    inject(pair)
    source = CaptureSource(pair.raw_root)

    outcome = SourceDeleteInterlock().delete_if_certified(pair.raw_root, pair.converted_root)

    assert not outcome.deleted
    assert _TARGET_EPISODE in outcome.flagged_episodes
    # Zero deletion: the raw source is preserved byte-for-byte.
    assert source.exists()
    assert source.episode_indices() == tuple(range(pair.episodes))
    # The episode is flagged on disk in the converted dataset's meta tree.
    flag = pair.converted_root / FLAG_SIDECAR_TEMPLATE.format(episode_index=_TARGET_EPISODE)
    assert flag.is_file()
