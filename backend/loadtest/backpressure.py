"""The backpressure-policy verifier — the CTR-WS shed rule, exercised on both sides.

`CG-5-05b` rests on one rule: above the `bufferedAmount` threshold the camera class is
shed and lease/command/telemetry are protected. This module does not restate that rule
— it imports `should_drop_under_backpressure`, the protected set, the drop set and the
threshold from `CTR-WS@v1` and fires them on synthetic buffer levels, proving the shed
actually happens for the camera above threshold and never happens for a protected class
at any level. Verifying the contract's own function (rather than a copy) is what makes
the check real: if the transport rule changed, this would move with it.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.ws.schema import (
    BACKPRESSURE_DROP_FRAMES,
    BACKPRESSURE_PROTECTED_FRAMES,
    BUFFERED_AMOUNT_THRESHOLD_BYTES,
    WsFrameType,
    should_drop_under_backpressure,
)

# Buffer levels the verifier probes: comfortably under the threshold, and over it.
# The over level is one byte past the threshold, so the check binds to the exact
# boundary the contract defines rather than to some arbitrary large number.
_UNDER_THRESHOLD_BYTES = BUFFERED_AMOUNT_THRESHOLD_BYTES // 2
_OVER_THRESHOLD_BYTES = BUFFERED_AMOUNT_THRESHOLD_BYTES + 1


@dataclass(frozen=True)
class BackpressurePolicyVerdict:
    """Whether the CTR-WS backpressure policy behaves as the single-WS design requires.

    Attributes:
        camera_shed_over_threshold: The camera class is shed once the buffer is over
            threshold (the head-of-line relief).
        camera_kept_under_threshold: The camera class is NOT shed below threshold (a
            healthy link is not degraded needlessly).
        protected_never_shed: No protected class is shed at any probed level.
        threshold_bytes: The `bufferedAmount` threshold the verdict was rendered at.
        violations: One line per rule that did not hold; empty when the policy is sound.
    """

    camera_shed_over_threshold: bool
    camera_kept_under_threshold: bool
    protected_never_shed: bool
    threshold_bytes: int
    violations: tuple[str, ...]

    @property
    def sound(self) -> bool:
        """Whether every backpressure rule held."""
        return not self.violations


def verify_backpressure_policy() -> BackpressurePolicyVerdict:
    """Exercise the CTR-WS shed rule on synthetic buffer levels and report the outcome.

    Returns:
        (BackpressurePolicyVerdict) The result of firing `should_drop_under_backpressure`
        for the camera class over and under threshold, and for every protected class at
        both levels.
    """
    violations: list[str] = []

    camera_shed_over = all(
        should_drop_under_backpressure(frame_type, _OVER_THRESHOLD_BYTES)
        for frame_type in BACKPRESSURE_DROP_FRAMES
    )
    if not camera_shed_over:
        violations.append("camera class is not shed above the bufferedAmount threshold")

    camera_kept_under = not any(
        should_drop_under_backpressure(frame_type, _UNDER_THRESHOLD_BYTES)
        for frame_type in BACKPRESSURE_DROP_FRAMES
    )
    if not camera_kept_under:
        violations.append("camera class is shed even below the threshold (over-eager degrade)")

    protected_never_shed = True
    for frame_type in BACKPRESSURE_PROTECTED_FRAMES:
        for level in (_UNDER_THRESHOLD_BYTES, _OVER_THRESHOLD_BYTES):
            if should_drop_under_backpressure(frame_type, level):
                protected_never_shed = False
                violations.append(
                    f"protected class {frame_type.value!r} was shed at {level} bytes — "
                    "a control/lease frame must never be dropped under backpressure"
                )

    return BackpressurePolicyVerdict(
        camera_shed_over_threshold=camera_shed_over,
        camera_kept_under_threshold=camera_kept_under,
        protected_never_shed=protected_never_shed,
        threshold_bytes=BUFFERED_AMOUNT_THRESHOLD_BYTES,
        violations=tuple(violations),
    )


def protected_frame_types() -> tuple[WsFrameType, ...]:
    """Return the CTR-WS protected frame set, for a report that lists what is protected.

    Returns:
        (tuple[WsFrameType, ...]) The frames never shed under backpressure.
    """
    return tuple(BACKPRESSURE_PROTECTED_FRAMES)
