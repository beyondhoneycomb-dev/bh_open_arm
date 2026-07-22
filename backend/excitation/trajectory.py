"""The per-joint exciting trajectory: a limit-respecting, index-addressable multisine.

`02b` §2.2 asks for a per-joint exciting trajectory whose band is a function of the
achieved logging frequency. This module builds it as a Schroeder-phased multisine —
a sum of harmonically spaced sinusoids inside the `ExcitationBand` — because spreading
energy across the band conditions the least-squares friction fit (`WP-2B-07`) while
the Schroeder phase keeps the crest factor low so the commanded torque does not spike.

Two properties the harness depends on:

* Every sample is a pure function of its integer index (`index / logging_frequency`
  is the sample time), so a resume from a recorded trajectory index reproduces exactly
  the sample the aborted run would have commanded — `02b` §2.3 ③, resume-by-index.
* A spec whose peak position excursion or peak velocity leaves the joint's bounds is
  refused at construction (`TrajectoryLimitError`), so an out-of-range trajectory can
  never reach the injection loop on a brakeless arm.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from backend.dynamics import ARM_JOINT_COUNT
from backend.excitation.band import ExcitationBand
from backend.excitation.constants import DEFAULT_HARMONIC_COUNT
from backend.excitation.errors import TrajectoryLimitError


@dataclass(frozen=True)
class JointBounds:
    """A single joint's position and velocity envelope, v2 convention.

    Attributes:
        position_min_rad: Lower position bound, radians.
        position_max_rad: Upper position bound, radians.
        velocity_max_rad_s: Peak allowed speed magnitude, radians/second.
    """

    position_min_rad: float
    position_max_rad: float
    velocity_max_rad_s: float


@dataclass(frozen=True)
class JointExcitation:
    """The excitation of one joint: a center pose and a peak amplitude about it.

    Attributes:
        center_rad: The pose the multisine oscillates about, radians (v2 convention).
        amplitude_rad: The peak single-side position excursion, radians. The multisine
            splits this across its harmonics, so `center ± amplitude` is the excursion
            envelope the bounds check uses.
    """

    center_rad: float
    amplitude_rad: float


@dataclass(frozen=True)
class TrajectorySample:
    """One index's per-joint targets, the unit the injection loop commands.

    Attributes:
        index: The trajectory index this sample is for.
        positions_rad: Per-joint target positions, radians, joint1..jointN.
        velocities_rad_s: Per-joint target velocities, radians/second, joint1..jointN.
    """

    index: int
    positions_rad: tuple[float, ...]
    velocities_rad_s: tuple[float, ...]


def _schroeder_phases(harmonic_count: int) -> tuple[float, ...]:
    """Return Schroeder phases for a flat-amplitude multisine of `harmonic_count` tones.

    The Schroeder phase `-k(k-1)π / N` minimises the crest factor of a flat multisine,
    which keeps the peak commanded excursion (and thus torque) close to its RMS rather
    than letting every tone align at `t=0`.

    Args:
        harmonic_count: Number of tones.

    Returns:
        (tuple[float, ...]) One phase per tone, radians.
    """
    return tuple(-math.pi * k * (k - 1) / harmonic_count for k in range(harmonic_count))


def _tone_frequencies(band: ExcitationBand, harmonic_count: int) -> tuple[float, ...]:
    """Return `harmonic_count` frequencies spread linearly across the band, Hz.

    A single-tone band collapses to the ceiling frequency; otherwise the tones are
    evenly spaced from `f_min_hz` to `f_max_hz` inclusive.

    Args:
        band: The identification band to fill.
        harmonic_count: Number of tones.

    Returns:
        (tuple[float, ...]) Tone frequencies in Hz, ascending.
    """
    if harmonic_count == 1:
        return (band.f_max_hz,)
    step = band.span_hz / (harmonic_count - 1)
    return tuple(band.f_min_hz + step * k for k in range(harmonic_count))


class ExcitingTrajectory:
    """A multisine exciting trajectory over `ARM_JOINT_COUNT` joints, addressable by index.

    Ownership/threading: immutable after construction. Every sample is derived on the
    fly from the tone table and the sample index, so the object holds no cursor and is
    safe to sample in any order — which is what makes resume-by-index exact.
    """

    def __init__(
        self,
        band: ExcitationBand,
        joints: Sequence[JointExcitation],
        bounds: Sequence[JointBounds],
        duration_s: float,
        harmonic_count: int = DEFAULT_HARMONIC_COUNT,
    ) -> None:
        """Build the trajectory and refuse any joint whose peaks leave its bounds.

        Args:
            band: The identification band the tones occupy (from `design_band`).
            joints: Per-joint excitation, one entry per arm joint.
            bounds: Per-joint position/velocity envelope, one entry per arm joint.
            duration_s: Session length in seconds; the sample count is
                `round(duration_s * band.logging_frequency_hz)`.
            harmonic_count: Number of tones in each joint's multisine.

        Raises:
            ValueError: On a joint/bounds count mismatch, a non-positive duration, or a
                harmonic count below one.
            TrajectoryLimitError: If a joint's peak position excursion or peak velocity
                leaves its bounds.
        """
        if len(joints) != ARM_JOINT_COUNT or len(bounds) != ARM_JOINT_COUNT:
            raise ValueError(
                f"expected {ARM_JOINT_COUNT} joints and bounds, got {len(joints)} joints "
                f"and {len(bounds)} bounds"
            )
        if duration_s <= 0.0:
            raise ValueError(f"duration must be positive, got {duration_s}")
        if harmonic_count < 1:
            raise ValueError(f"harmonic_count must be at least 1, got {harmonic_count}")

        self._band = band
        self._joints = tuple(joints)
        self._bounds = tuple(bounds)
        self._frequencies_hz = _tone_frequencies(band, harmonic_count)
        self._phases = _schroeder_phases(harmonic_count)
        self._sample_count = round(duration_s * band.logging_frequency_hz)
        if self._sample_count < 1:
            raise ValueError(
                f"duration {duration_s} s at {band.logging_frequency_hz} Hz yields no samples"
            )
        self._assert_within_bounds()

    @property
    def band(self) -> ExcitationBand:
        """The identification band this trajectory fills."""
        return self._band

    @property
    def sample_count(self) -> int:
        """The number of indexed samples in the session (`0 .. sample_count - 1`)."""
        return self._sample_count

    def peak_velocity_rad_s(self, joint_index: int) -> float:
        """The worst-case speed magnitude a joint reaches, radians/second.

        The bound is the sum of per-tone velocity amplitudes (`a_k · 2π f_k`); it is the
        value the bounds check enforces and the one a caller compares against the joint's
        rated speed.

        Args:
            joint_index: Zero-based joint index.

        Returns:
            (float) Peak speed magnitude, radians/second.
        """
        per_tone = self._joints[joint_index].amplitude_rad / len(self._frequencies_hz)
        return sum(per_tone * math.tau * f for f in self._frequencies_hz)

    def sample(self, index: int) -> TrajectorySample:
        """Return the per-joint targets at a trajectory index.

        The sample time is `index / logging_frequency_hz`, and each joint's target is the
        Schroeder-phased multisine evaluated there. Being a pure function of `index` is
        what makes a resume from a recorded index reproduce the aborted run's sample.

        Args:
            index: Trajectory index in `0 .. sample_count - 1`.

        Returns:
            (TrajectorySample) The positions and velocities to command at `index`.

        Raises:
            IndexError: If `index` is outside `0 .. sample_count - 1`.
        """
        if not 0 <= index < self._sample_count:
            raise IndexError(f"trajectory index {index} out of range 0..{self._sample_count - 1}")
        t = index / self._band.logging_frequency_hz
        positions: list[float] = []
        velocities: list[float] = []
        for joint in self._joints:
            position, velocity = self._joint_state(joint, t)
            positions.append(position)
            velocities.append(velocity)
        return TrajectorySample(
            index=index,
            positions_rad=tuple(positions),
            velocities_rad_s=tuple(velocities),
        )

    def _joint_state(self, joint: JointExcitation, t: float) -> tuple[float, float]:
        """Evaluate one joint's multisine position and velocity at time `t` seconds."""
        per_tone = joint.amplitude_rad / len(self._frequencies_hz)
        position = joint.center_rad
        velocity = 0.0
        for frequency, phase in zip(self._frequencies_hz, self._phases, strict=True):
            omega = math.tau * frequency
            angle = omega * t + phase
            position += per_tone * math.sin(angle)
            velocity += per_tone * omega * math.cos(angle)
        return position, velocity

    def _assert_within_bounds(self) -> None:
        """Refuse any joint whose peak excursion or peak velocity leaves its bounds.

        The peak position excursion is bounded by `center ± amplitude` (the worst case in
        which every tone aligns), and the peak velocity by the summed per-tone velocity
        amplitudes. Both are checked before the trajectory is usable, so nothing
        out-of-range can be commanded.
        """
        for index, (joint, bound) in enumerate(zip(self._joints, self._bounds, strict=True)):
            low = joint.center_rad - joint.amplitude_rad
            high = joint.center_rad + joint.amplitude_rad
            if low < bound.position_min_rad or high > bound.position_max_rad:
                raise TrajectoryLimitError(
                    f"joint {index}: excursion [{low:.4f}, {high:.4f}] rad leaves bounds "
                    f"[{bound.position_min_rad:.4f}, {bound.position_max_rad:.4f}] rad"
                )
            peak_velocity = self.peak_velocity_rad_s(index)
            if peak_velocity > bound.velocity_max_rad_s:
                raise TrajectoryLimitError(
                    f"joint {index}: peak velocity {peak_velocity:.4f} rad/s exceeds bound "
                    f"{bound.velocity_max_rad_s:.4f} rad/s"
                )
