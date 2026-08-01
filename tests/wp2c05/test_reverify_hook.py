"""The `NFR-SAF-007` hold-send-period acceptance: deferred offline, run on a real candump.

The quantitative acceptance — the Cat-2 hold's CAN send period stays below the RID-9
`TIMEOUT` — cannot run on a desktop: the RID-9 timeout is `[결정필요]` (unread without a
CAN bus) and the true send period needs a hardware candump. Offline it is skipped with a
reason, never asserted green (`THE ONE RULE`); the moment `FIXTURE_ENV_VAR` names a
capture directory the acceptance runs over those timestamps and can fail. The synthetic
tests exercise the same check both directions, and neither number is ever supplied by the
test — both come from the capture, so the hook cannot manufacture a pass.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.reaction import (
    FIXTURE_ENV_VAR,
    fixture_dir_from_env,
    reverify_from_fixture,
)

# Read once, at collection: the operator names the directory on the pytest command line, so
# the skip decision and the assertion below must see the same value. The skip turns on the raw
# string rather than the resolved directory — a mistyped path is a typo to report, not a
# deferral to honour, and resolving first would silently turn it back into a skip.
_FIXTURE_ENV_RAW = os.environ.get(FIXTURE_ENV_VAR, "")

_DEFERRED_REASON = (
    "NFR-SAF-007 hold-send-period is torque-ON / real-bus: the RID-9 TIMEOUT is [결정필요] and "
    f"the send period needs a hardware candump; set {FIXTURE_ENV_VAR} to a directory of "
    "decoded candump captures to run the acceptance here"
)


@pytest.mark.skipif(not _FIXTURE_ENV_RAW, reason=_DEFERRED_REASON)
def test_hold_send_period_against_the_real_fixture() -> None:
    """Every real capture's largest hold-send gap stays under that capture's RID-9 timeout."""
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None, (
        f"{FIXTURE_ENV_VAR} names {_FIXTURE_ENV_RAW!r}, which is not a directory"
    )
    verdicts = reverify_from_fixture(fixture_dir)
    assert verdicts, f"no hold-send capture in {fixture_dir}"
    for verdict in verdicts:
        assert verdict.within_deadline, (
            f"{verdict.source}: largest hold-send gap {verdict.max_interval_sec} s reached the "
            f"RID-9 timeout {verdict.rid9_timeout_sec} s — the motors time out during the hold"
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
