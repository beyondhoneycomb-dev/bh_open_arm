"""The received-frame data model: a per-arm pose plus both timestamps and validity.

`VrFrame` is what `read_latest()` returns and what WP-3B-09/10 consume. It reuses
the frozen `CTR-TEL@v1` `TeleopSample` for the dual-timestamp + overall-validity
facts (both the source `t` and the PC receive instant, never one collapsed into
the other) and adds the per-arm decomposition the UDP wire carries: an `ArmPose`
per side with its own validity, world-frame pose and grip.

`frame_applied` is the static declaration that the `R_ROBOT` frame change has
already happened, so a downstream consumer asserts it and does not re-apply the
transform (`05` §2.8, no double transform).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from backend.teleop.vr_udp.transform import WorldPose
from contracts.teleop import TeleopSample, TeleopValidity


@dataclass(frozen=True)
class ArmPose:
    """One arm's decoded state within a received frame.

    Attributes:
        side: The arm, `"left"` or `"right"`.
        validity: This arm's tracking validity (from the wire `vl`/`vr`).
        world_pose: The transformed robot-world EE target, or None when the arm is
            INVALID — an INVALID arm withholds its pose (`05` §2.14), so the field
            is absent rather than a stale or fabricated value.
        grip: The analog grip in [0, 1] (the clutch input), carried through untouched.
    """

    side: str
    validity: TeleopValidity
    world_pose: WorldPose | None
    grip: float

    @property
    def is_publishable(self) -> bool:
        """Whether this arm's pose is published (OK or STALE, never INVALID)."""
        return self.validity.is_publishable


@dataclass(frozen=True)
class VrFrame:
    """One received VR datagram, parsed, transformed and dual-timestamped.

    Attributes:
        teleop_sample: The `CTR-TEL@v1` sample carrying the source `t` (CLIENT
            clock, age input), the PC receive instant (SERVER `CLOCK_MONOTONIC`
            ns) and the overall validity — both timestamps preserved distinctly.
        arms: Per-arm decoded state, keyed by side.
        buttons: Face-button state (`a`/`b`/`x`/`y`).
        frame_applied: True — the `R_ROBOT` world-frame transform was applied by
            this source; a consumer must not re-apply it.
    """

    teleop_sample: TeleopSample
    arms: Mapping[str, ArmPose]
    buttons: Mapping[str, bool]
    frame_applied: bool

    @property
    def source_ts(self) -> float:
        """The headset source time `t` (CLIENT clock)."""
        return self.teleop_sample.source_ts

    @property
    def receive_mono_ns(self) -> int:
        """The PC receive instant (SERVER `CLOCK_MONOTONIC` nanoseconds)."""
        return self.teleop_sample.receive_mono_ns

    @property
    def validity(self) -> TeleopValidity:
        """The overall tracking validity (from the wire `v`)."""
        return self.teleop_sample.validity

    @property
    def is_publishable(self) -> bool:
        """Whether the frame is published (overall OK or STALE, never INVALID)."""
        return self.teleop_sample.validity.is_publishable

    def arm(self, side: str) -> ArmPose:
        """Return the decoded state for one arm.

        Args:
            side: `"left"` or `"right"`.

        Returns:
            (ArmPose) That arm's decoded state.

        Raises:
            KeyError: If `side` is not an arm carried by this frame.
        """
        return self.arms[side]
