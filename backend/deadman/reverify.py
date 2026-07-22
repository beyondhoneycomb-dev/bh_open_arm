"""The on-HW re-verification hook for the deadman stop (plan 02a §4.1).

The offline suite proves the deadman *decides* a latch on expiry and that the reused
scheduler *emits* SAFETY_LATCH_HOLD. What it cannot prove without a rig is that the
hold frame actually reaches the CAN bus at expiry and that no motion frame follows —
the real-CAN candump confirmation. That step is DEFERRED (this dev host has no CAN),
and it must never be asserted green here: a faked bus-stop green is a safety lie, a
human trusts it before energising a 40 Nm arm with no holding brake.

What is NOT deferred is the *check itself*. This module confirms the deadman contract
on an already-classified frame timeline, so the hook is a real predicate — proven
here against synthetic timelines — and only the physical capture is left to the rig.
It stays deliberately distinct from `WP-2A-06`, which measures stop *latency*
histograms; this confirms the deadman *contract* (stop is a hold at/after the
server-clock expiry, and nothing moves after it), not a timing figure.

Classifying raw candump bytes into hold-vs-motion frames is the rig-capture step
(it decodes MIT frames), so the timeline this consumes is the boundary: the rig
produces it, the tests synthesise it, and the contract check is identical for both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# The environment variable naming a captured stop timeline from the rig. Until it is
# set, the live re-verification defers rather than asserting anything.
CANDUMP_CAPTURE_ENV_VAR = "OPENARM_DEADMAN_STOP_CAPTURE"


class FrameKind(Enum):
    """The two frame classes the deadman contract distinguishes on the bus.

    HOLD is a position-hold (the SAFETY_LATCH_HOLD shape: last positions, zero
    feed-forward torque); MOTION is a fresh commanded target. A torque-disable is not
    a category here on purpose — the stop path never cuts torque (`04` NFR-MAN-002),
    so a decoder that saw one would classify it as neither, and the post-expiry
    window check (every frame is a HOLD) rejects a stop that is anything but a hold.
    """

    HOLD = "hold"
    MOTION = "motion"


@dataclass(frozen=True)
class ObservedFrame:
    """One classified CAN frame from a captured stop timeline.

    Attributes:
        mono_server: The frame's arrival time on the server monotonic clock, in
            seconds — the same clock the lease expiry is judged on.
        kind: Whether the frame is a position-hold or a commanded motion.
    """

    mono_server: float
    kind: FrameKind


@dataclass(frozen=True)
class ReverifyReport:
    """The verdict of confirming a captured stop against the deadman contract.

    Attributes:
        confirmed: True only when every contract check passed.
        checks: The names of the checks that were evaluated.
        mismatches: One message per failed check; empty when confirmed.
    """

    confirmed: bool
    checks: tuple[str, ...]
    mismatches: tuple[str, ...]


_CHECK_STOP_PRESENT = "stop_frame_present_at_or_after_expiry"
_CHECK_NO_MOTION_AFTER = "no_motion_after_expiry"
_CHECK_HELD_CONTINUOUSLY = "held_continuously_from_expiry"


def reverify_expiry_stop(
    frames: tuple[ObservedFrame, ...], expiry_mono_server: float
) -> ReverifyReport:
    """Confirm a captured stop timeline satisfies the deadman contract on the bus.

    The three checks are the bus-level projection of the offline contract:

    - a hold frame is present at or after the server-clock expiry (the stop happened,
      and it happened at expiry — not before it, which would mean something other
      than the deadman stopped the arm);
    - no motion frame appears at or after expiry (the latch holds — nothing resumed
      on the bus, the U-4 property that a post-expiry renewal cannot un-stop the arm);
    - every frame from expiry onward is a hold (the stop stays a position-hold; it is
      never a torque cut or a resumed command).

    Args:
        frames: The classified stop timeline, in arrival order.
        expiry_mono_server: The lease's server-clock expiry, the boundary the checks
            are taken around.

    Returns:
        (ReverifyReport) The verdict; `confirmed` only when all three checks pass.
    """
    checks = (_CHECK_STOP_PRESENT, _CHECK_NO_MOTION_AFTER, _CHECK_HELD_CONTINUOUSLY)
    mismatches: list[str] = []

    after_expiry = [frame for frame in frames if frame.mono_server >= expiry_mono_server]

    if not any(frame.kind is FrameKind.HOLD for frame in after_expiry):
        mismatches.append("no hold frame observed at or after the server-clock expiry")

    motion_after = [frame for frame in after_expiry if frame.kind is FrameKind.MOTION]
    if motion_after:
        mismatches.append(
            f"{len(motion_after)} motion frame(s) after expiry — the latch did not hold on the bus"
        )

    if after_expiry and not all(frame.kind is FrameKind.HOLD for frame in after_expiry):
        mismatches.append("the post-expiry window is not held continuously")

    return ReverifyReport(confirmed=not mismatches, checks=checks, mismatches=tuple(mismatches))


def load_capture(path: Path) -> tuple[tuple[ObservedFrame, ...], float]:
    """Load a rig-captured stop timeline and its expiry from a JSON capture file.

    The capture is the boundary artifact the rig produces after decoding candump into
    classified frames. Its shape is `{"expiry_mono_server": float, "frames":
    [{"mono_server": float, "kind": "hold"|"motion"}, ...]}`.

    Args:
        path: The capture file.

    Returns:
        (tuple) The frames and the expiry time to check them against.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    frames = tuple(
        ObservedFrame(mono_server=float(entry["mono_server"]), kind=FrameKind(entry["kind"]))
        for entry in document["frames"]
    )
    return frames, float(document["expiry_mono_server"])


def reverify_from_capture(path: Path) -> ReverifyReport:
    """Run the contract check against a captured stop timeline on disk.

    Args:
        path: A capture file in the `load_capture` shape.

    Returns:
        (ReverifyReport) The verdict for the captured stop.
    """
    frames, expiry_mono_server = load_capture(path)
    return reverify_expiry_stop(frames, expiry_mono_server)
