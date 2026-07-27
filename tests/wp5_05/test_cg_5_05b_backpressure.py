"""CG-5-05b (policy) — the CTR-WS backpressure rule sheds camera, protects control.

The ordering verdict rests on this rule, so it is verified directly against the
contract's own `should_drop_under_backpressure`: camera is shed above the threshold,
kept below it, and no protected class is ever shed at any level. Firing the contract
function (not a copy) is what makes the check move if the transport rule ever changes.
"""

from __future__ import annotations

from backend.loadtest import verify_backpressure_policy
from contracts.ws.schema import (
    BACKPRESSURE_PROTECTED_FRAMES,
    BUFFERED_AMOUNT_THRESHOLD_BYTES,
    WsFrameType,
    should_drop_under_backpressure,
)


def test_policy_is_sound() -> None:
    verdict = verify_backpressure_policy()
    assert verdict.sound
    assert verdict.camera_shed_over_threshold
    assert verdict.camera_kept_under_threshold
    assert verdict.protected_never_shed
    assert verdict.violations == ()


def test_camera_shed_only_over_threshold() -> None:
    assert not should_drop_under_backpressure(WsFrameType.CAMERA, BUFFERED_AMOUNT_THRESHOLD_BYTES)
    assert should_drop_under_backpressure(WsFrameType.CAMERA, BUFFERED_AMOUNT_THRESHOLD_BYTES + 1)


def test_protected_frames_never_shed_even_far_over_threshold() -> None:
    far_over = BUFFERED_AMOUNT_THRESHOLD_BYTES * 1000
    for frame_type in BACKPRESSURE_PROTECTED_FRAMES:
        assert not should_drop_under_backpressure(frame_type, far_over)


def test_verdict_reads_the_contract_threshold() -> None:
    # Reuse, not fork: the verdict's threshold is the CTR-WS constant, not a local copy.
    assert verify_backpressure_policy().threshold_bytes == BUFFERED_AMOUNT_THRESHOLD_BYTES
