"""A deterministic synthetic VR pose stream for the teleoperator path.

`02b` §5.2 WP-3A-06: the VR teleoperator (`WP-3B-07`) is built and tested against
this stream, never a real headset. The stream is deterministic in a seed and its
sample index, so a coordinate-transform or clutch test can assert an exact pose
and reproduce it.

The contract-shaped part of each sample is a `CTR-TEL@v1` `TeleopSample`: the two
timestamps are preserved (the headset source `t` on the CLIENT clock as an age
input, the PC receive instant on the SERVER `CLOCK_MONOTONIC`), and the tracking
validity is the three-level `OK`/`STALE`/`INVALID` model — all imported from the
frozen contract, none restated (`02b` §5.0b). Alongside it the sample carries the
`WP-3B-07` UDP payload shape (per-arm controller pose, grips, face buttons, the
`v`/`vl`/`vr` validity wire values) so the receiver's parse path has real input.
`STALE` still publishes the last pose; `INVALID` is the sample that must reset the
downstream smoother, so both are injectable by index.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from contracts.prim import AGE_INPUT_ROLE, CLOCK_SOURCE
from contracts.teleop import TeleopSample, TeleopValidity
from contracts.teleop.schema import RECEIVE_TS_ROLE, SOURCE_TS_ROLE, verify_source_is_age_input

# The nanosecond period between successive receive instants at the stream's
# nominal rate. Named so the receive clock advances by a contract-derived step,
# not a bare literal, and 90 Hz is the VR headset frame rate the source models.
VR_STREAM_HZ = 90
NANOS_PER_SECOND = 1_000_000_000
_RECEIVE_PERIOD_NS = NANOS_PER_SECOND // VR_STREAM_HZ

# The source clock ticks in seconds; one source step is the same 90 Hz period.
_SOURCE_PERIOD_S = 1.0 / VR_STREAM_HZ

# The two arms a bimanual VR sample carries, in the `CTR-PRIM@v1` arm order.
_ARM_SIDES = ("left", "right")


@dataclass(frozen=True)
class VrPoseSample:
    """One received VR sample: its contract facts and its UDP payload.

    Attributes:
        teleop_sample: The `CTR-TEL@v1` sample — dual timestamps and validity.
        positions: Per-arm controller position `(x, y, z)`, deterministic.
        quaternions: Per-arm controller orientation `(x, y, z, w)`.
        grips: Per-arm grip value in `[0, 1]` (the clutch input).
        buttons: The face-button state (`a`, `b`, `x`, `y`).
    """

    teleop_sample: TeleopSample
    positions: Mapping[str, tuple[float, float, float]]
    quaternions: Mapping[str, tuple[float, float, float, float]]
    grips: Mapping[str, float]
    buttons: Mapping[str, bool]

    @property
    def validity(self) -> TeleopValidity:
        """The tracking validity of this sample (OK/STALE/INVALID)."""
        return self.teleop_sample.validity

    @property
    def is_publishable(self) -> bool:
        """Whether the receiver publishes this sample's pose (OK or STALE)."""
        return self.teleop_sample.validity.is_publishable

    def udp_payload(self) -> dict[str, object]:
        """Render the sample in the `WP-3B-07` UDP JSON keyset shape.

        The `t` field is the source time, `lc`/`rc` the per-arm positions, `lt`/`rt`
        the per-arm quaternions, `lg`/`rg` the grips, `a`/`b`/`x`/`y` the buttons,
        and `v`/`vl`/`vr` the validity wire values (`05` §2.7). This is input to the
        receiver, not a redefinition of any primitive.

        Returns:
            (dict[str, object]) The single-sample UDP payload.
        """
        return {
            "t": self.teleop_sample.source_ts,
            "lc": list(self.positions["left"]),
            "rc": list(self.positions["right"]),
            "lt": list(self.quaternions["left"]),
            "rt": list(self.quaternions["right"]),
            "lg": self.grips["left"],
            "rg": self.grips["right"],
            "a": self.buttons["a"],
            "b": self.buttons["b"],
            "x": self.buttons["x"],
            "y": self.buttons["y"],
            "v": int(self.validity),
            "vl": int(self.validity),
            "vr": int(self.validity),
        }


@dataclass(frozen=True)
class SyntheticVrPoseStream:
    """A deterministic sequence of `VrPoseSample`s along a smooth trajectory.

    The pose walks a smooth circular path so a coordinate-transform test sees
    continuous motion; each sample's timestamps advance by the stream period.
    Validity is `OK` unless an index is injected as `STALE` or `INVALID`.

    Attributes:
        start_source_ts: The source time of sample 0, seconds on the CLIENT clock.
        start_receive_mono_ns: The receive instant of sample 0, SERVER nanoseconds.
        stale_indices: Sample indices to mark `STALE` (still published).
        invalid_indices: Sample indices to mark `INVALID` (pose withheld, reset).
    """

    start_source_ts: float = 0.0
    start_receive_mono_ns: int = 0
    stale_indices: frozenset[int] = field(default_factory=frozenset)
    invalid_indices: frozenset[int] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """Reject an index marked both STALE and INVALID — a sample is one validity."""
        overlap = self.stale_indices & self.invalid_indices
        if overlap:
            raise ValueError(f"indices {sorted(overlap)} marked both STALE and INVALID")
        # The source timestamp is an age input, never the latency authority; assert
        # the pin at construction so a fixture cannot hand a consumer a mis-owned clock.
        verify_source_is_age_input(SOURCE_TS_ROLE)

    def validity_at(self, index: int) -> TeleopValidity:
        """The tracking validity injected at a sample index (OK by default)."""
        if index in self.invalid_indices:
            return TeleopValidity.INVALID
        if index in self.stale_indices:
            return TeleopValidity.STALE
        return TeleopValidity.OK

    def sample(self, index: int) -> VrPoseSample:
        """Build the deterministic sample at an index.

        Args:
            index: The 0-based sample position.

        Returns:
            (VrPoseSample) The pose, timestamps and validity at this index.
        """
        angle = index * 0.05
        positions = {
            side: (
                round(0.30 * math.cos(angle) + offset, 6),
                round(0.30 * math.sin(angle), 6),
                round(0.10 * math.sin(angle * 0.5), 6),
            )
            for side, offset in zip(_ARM_SIDES, (-0.20, 0.20), strict=True)
        }
        quaternions = {
            side: (0.0, round(math.sin(angle / 2), 6), 0.0, round(math.cos(angle / 2), 6))
            for side in _ARM_SIDES
        }
        grips = {side: round(0.5 + 0.5 * math.sin(angle), 6) for side in _ARM_SIDES}
        buttons = {"a": index % 8 == 0, "b": False, "x": index % 16 == 0, "y": False}
        teleop_sample = TeleopSample(
            source_ts=round(self.start_source_ts + index * _SOURCE_PERIOD_S, 9),
            receive_mono_ns=self.start_receive_mono_ns + index * _RECEIVE_PERIOD_NS,
            validity=self.validity_at(index),
        )
        return VrPoseSample(
            teleop_sample=teleop_sample,
            positions=positions,
            quaternions=quaternions,
            grips=grips,
            buttons=buttons,
        )

    def samples(self, count: int) -> list[VrPoseSample]:
        """Build a run of `count` deterministic samples.

        Args:
            count: The number of samples to emit.

        Returns:
            (list[VrPoseSample]) Samples 0..count-1 in order.
        """
        return [self.sample(index) for index in range(count)]

    def published(self, count: int) -> list[VrPoseSample]:
        """The samples a receiver would publish (OK or STALE, never INVALID).

        Args:
            count: The number of samples in the run.

        Returns:
            (list[VrPoseSample]) The publishable subset, in order.
        """
        return [sample for sample in self.samples(count) if sample.is_publishable]


def timestamp_roles() -> tuple[str, str]:
    """Return the (source, receive) clock roles this stream preserves.

    Both come from `CTR-PRIM@v1`: the source is the age-input CLIENT clock, the
    receive instant is the SERVER `CLOCK_MONOTONIC`. Exposed so a consumer can
    assert the fixture kept them distinct (`02b` §5.0b row 2).

    Returns:
        (tuple[str, str]) The source-timestamp role and the receive-timestamp role.
    """
    assert SOURCE_TS_ROLE == AGE_INPUT_ROLE  # the source is an age input, not authority
    assert CLOCK_SOURCE  # the receive clock is the shared monotonic source
    return (SOURCE_TS_ROLE.value, RECEIVE_TS_ROLE.value)


def validity_wire_values() -> Sequence[int]:
    """The `v`/`vl`/`vr` UDP wire values, from the frozen `TeleopValidity`.

    Returns:
        (Sequence[int]) `[0, 1, 2]` for OK/STALE/INVALID, in enum order.
    """
    return [int(level) for level in TeleopValidity]
