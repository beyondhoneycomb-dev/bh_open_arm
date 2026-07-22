"""The deferred on-HW candump confirmation — hook logic runs here, the live capture defers.

The real-CAN confirmation (stop frame reaches the bus at expiry, nothing moves after)
needs a rig this dev host does not have, so the live path is SKIPPED with its reason
and never asserted — a faked bus-stop green is a safety lie. What runs here is the
*hook logic*: the contract check is exercised against synthetic stop timelines, so it
is proven to be a real predicate (a clean stop confirms; a post-expiry motion, a
missing stop, and a torque resume are each caught) before the rig ever runs it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.deadman.reverify import (
    CANDUMP_CAPTURE_ENV_VAR,
    FrameKind,
    ObservedFrame,
    reverify_expiry_stop,
    reverify_from_capture,
)

_EXPIRY = 10.0


def _frame(offset: float, kind: FrameKind) -> ObservedFrame:
    """A frame at `offset` seconds relative to the expiry."""
    return ObservedFrame(mono_server=_EXPIRY + offset, kind=kind)


def test_clean_stop_capture_confirms() -> None:
    """Motion up to expiry, then held continuously with nothing moving, confirms."""
    frames = (
        _frame(-0.003, FrameKind.MOTION),
        _frame(-0.001, FrameKind.MOTION),
        _frame(0.000, FrameKind.HOLD),
        _frame(0.001, FrameKind.HOLD),
        _frame(0.002, FrameKind.HOLD),
    )
    report = reverify_expiry_stop(frames, _EXPIRY)
    assert report.confirmed
    assert report.mismatches == ()


def test_post_expiry_motion_is_caught() -> None:
    """A motion frame after expiry means the latch did not hold — it is rejected."""
    frames = (
        _frame(0.000, FrameKind.HOLD),
        _frame(0.001, FrameKind.HOLD),
        _frame(0.002, FrameKind.MOTION),  # the arm moved after the stop
    )
    report = reverify_expiry_stop(frames, _EXPIRY)
    assert not report.confirmed
    assert any("latch did not hold" in message for message in report.mismatches)


def test_missing_stop_is_caught() -> None:
    """No hold frame at or after expiry means no stop was observed — rejected."""
    frames = (
        _frame(-0.002, FrameKind.MOTION),
        _frame(-0.001, FrameKind.HOLD),  # held only before expiry, nothing after
    )
    report = reverify_expiry_stop(frames, _EXPIRY)
    assert not report.confirmed
    assert any("no hold frame" in message for message in report.mismatches)


def test_resume_after_a_held_window_is_caught() -> None:
    """A hold that later resumes to motion is rejected — a stop that un-stops."""
    frames = (
        _frame(0.000, FrameKind.HOLD),
        _frame(0.001, FrameKind.HOLD),
        _frame(0.010, FrameKind.MOTION),
        _frame(0.011, FrameKind.MOTION),
    )
    report = reverify_expiry_stop(frames, _EXPIRY)
    assert not report.confirmed


def test_from_capture_round_trips(tmp_path: Path) -> None:
    """The disk-capture loader feeds the identical check the live path will run."""
    capture = tmp_path / "stop.json"
    capture.write_text(
        json.dumps(
            {
                "expiry_mono_server": _EXPIRY,
                "frames": [
                    {"mono_server": _EXPIRY - 0.001, "kind": "motion"},
                    {"mono_server": _EXPIRY, "kind": "hold"},
                    {"mono_server": _EXPIRY + 0.001, "kind": "hold"},
                ],
            }
        ),
        encoding="utf-8",
    )
    report = reverify_from_capture(capture)
    assert report.confirmed


@pytest.mark.skipif(
    CANDUMP_CAPTURE_ENV_VAR not in os.environ,
    reason=(
        f"HW-DEFERRED: the real-CAN candump confirmation needs a rig. Set "
        f"{CANDUMP_CAPTURE_ENV_VAR} to a captured stop timeline (candump decoded to "
        f"hold/motion frames around the lease expiry) to re-verify the stop live. Never "
        f"asserted offline — a faked bus-stop green is a safety lie before a 40 Nm arm."
    ),
)
def test_reverify_against_real_candump_capture() -> None:
    """Deferred live path: confirm the deadman stop against a real rig capture."""
    capture = Path(os.environ[CANDUMP_CAPTURE_ENV_VAR])
    report = reverify_from_capture(capture)
    assert report.confirmed, f"live deadman stop re-verification failed: {report.mismatches}"
