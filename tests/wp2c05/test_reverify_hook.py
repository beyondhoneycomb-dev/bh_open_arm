"""The deferred `NFR-SAF-007` hold-send-period acceptance: skipped-with-reason + hook.

The quantitative acceptance — the Cat-2 hold's CAN send period stays below the RID-9
`TIMEOUT` — cannot run on this host: the RID-9 timeout is `[결정필요]` (unread without a
CAN bus) and the true send period needs a hardware candump. So it is deferred, never
asserted green (`THE ONE RULE`). This test proves the deferral is honest: without a real
fixture it skips with a reason, and the re-verification hook, run over synthetic
captures, applies the same deadline check both directions — a gap under the timeout
passes, a gap that reaches it fails, and the hook cannot manufacture a pass because both
numbers come from the capture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.reaction import (
    fixture_dir_from_env,
    reverify_from_fixture,
)


def test_hold_send_period_is_deferred_without_a_real_fixture() -> None:
    """With no real candump fixture named, the quantitative acceptance is skipped."""
    if fixture_dir_from_env() is not None:
        pytest.skip("a real candump fixture is present; the on-host deferral does not apply")
    pytest.skip(
        "NFR-SAF-007 hold-send-period is torque-ON / real-bus: RID-9 TIMEOUT is [결정필요] and "
        "the send period needs a hardware candump — deferred, re-verified by the fixture hook"
    )


def _write_capture(directory: Path, name: str, timestamps: list[float], timeout: float) -> None:
    """Write one synthetic candump capture the hook can re-verify."""
    payload = {"send_timestamps_sec": timestamps, "rid9_timeout_sec": timeout}
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def test_reverify_hook_passes_a_capture_under_the_deadline(tmp_path: Path) -> None:
    """A capture whose largest send gap is below the RID-9 timeout is within the deadline."""
    _write_capture(tmp_path, "j0.json", [0.0, 0.001, 0.002, 0.003], timeout=0.01)
    verdicts = reverify_from_fixture(tmp_path)
    assert len(verdicts) == 1
    assert verdicts[0].within_deadline
    assert verdicts[0].max_interval_sec == pytest.approx(0.001)


def test_reverify_hook_fails_a_capture_that_reaches_the_deadline(tmp_path: Path) -> None:
    """A capture with a send gap at or above the timeout fails — the hook cannot fake green."""
    _write_capture(tmp_path, "j1.json", [0.0, 0.001, 0.030], timeout=0.01)
    verdicts = reverify_from_fixture(tmp_path)
    assert not verdicts[0].within_deadline
    assert verdicts[0].max_interval_sec == pytest.approx(0.029)


def test_reverify_hook_refuses_an_empty_fixture_dir(tmp_path: Path) -> None:
    """An empty fixture directory is an error, not a vacuous pass."""
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)
