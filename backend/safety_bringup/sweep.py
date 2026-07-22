"""The PG-VEL-001 sweep publication gate: three constraints, or no artifact.

`03` §5.6.0 / §5.6 make the sweep a *verification under a limiter*, never a search for a
limit. Three constraints must hold together, and if any is missing the artifact is refused
(acceptance ⑨-a):

  1. single joint — one joint at a time; a multi-joint sweep reaches unplanned
     configurations at a composed speed.
  2. mechanically constrained — the joint's reach is physically bounded, inside the
     PG-SAFE-001 support coverage.
  3. under the bootstrap limiter — no commanded velocity exceeds the derived bootstrap
     limiter (`velocity.bootstrap_limiter_rad_s`). Raising the limiter to match an
     observation is self-approval and is not a variant (`03` §5.6.0).

What runs here is the *gate*: the constraint check and the "zero commands over the limiter"
check over the commanded values. The tracking error itself — commanded speed against
measured speed — needs the powered arm and is produced only from a real capture
(`reverify`); this module never manufactures a tracking verdict offline, because a faked
sweep pass is a safety lie.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.safety_bringup.velocity import bootstrap_limiter_rad_s


class SweepPublicationRefusedError(Exception):
    """Raised when a sweep artifact fails one of the three mandatory constraints (⑨-a).

    Refusing publication is the whole gate: an artifact that dropped a constraint would
    read as a validated limit while resting on an unvalidated or unprotected sweep.
    """


@dataclass(frozen=True)
class SweepConstraints:
    """The three assertions a publishable sweep must carry (`03` §5.6.0, acceptance ⑨-a).

    Attributes:
        single_joint: The sweep moved exactly one joint.
        mechanically_constrained: The joint reach was physically bounded during the sweep.
    """

    single_joint: bool
    mechanically_constrained: bool


@dataclass(frozen=True)
class SweepSample:
    """One commanded (and, from a real capture, measured) velocity sample.

    Attributes:
        commanded_rad_s: The velocity commanded this sample, rad/s.
        measured_rad_s: The measured joint velocity, rad/s — present only in a real
            capture; None offline, where no tracking verdict may be produced.
    """

    commanded_rad_s: float
    measured_rad_s: float | None


@dataclass(frozen=True)
class SweepPublication:
    """The result of admitting a single-joint sweep past the publication gate.

    Attributes:
        joint_index: The joint that was swept.
        limiter_rad_s: The bootstrap limiter ceiling asserted for this joint.
        commands_over_limiter: Count of commanded samples that exceeded the limiter —
            zero for a publishable sweep (acceptance ⑨-b log).
        tracking_error_rad_s: Per-sample |commanded - measured|, present only when the
            capture carried measured data; empty offline (the tracking verdict is deferred).
    """

    joint_index: int
    limiter_rad_s: float
    commands_over_limiter: int
    tracking_error_rad_s: tuple[float, ...]


def assert_sweep_publishable(
    joint_index: int,
    samples: tuple[SweepSample, ...],
    constraints: SweepConstraints,
) -> SweepPublication:
    """Admit a sweep only when all three constraints hold (⑨-a), and log limiter overruns.

    The bootstrap limiter for the joint is taken from the derivation, never from the
    observation. A commanded sample over the limiter both fails the third constraint and
    is counted; either way the artifact is refused. The tracking error is computed only for
    samples that carry a measurement, so an offline (measurement-free) sweep yields an empty
    tracking vector rather than a fabricated pass.

    Args:
        joint_index: Zero-based arm joint index being swept.
        samples: The commanded (and optionally measured) velocity samples.
        constraints: The single-joint and mechanically-constrained assertions.

    Returns:
        (SweepPublication) The admitted sweep with its overrun count and tracking vector.

    Raises:
        SweepPublicationRefusedError: If the sweep is not single-joint, not mechanically
            constrained, or any commanded velocity exceeds the bootstrap limiter.
    """
    if not constraints.single_joint:
        raise SweepPublicationRefusedError(
            "sweep is not single-joint; multi-joint sweeps reach unplanned configurations "
            "(03 §5.6.0, acceptance ⑨-a)"
        )
    if not constraints.mechanically_constrained:
        raise SweepPublicationRefusedError(
            "sweep joint reach was not mechanically constrained; a sweep must run inside the "
            "PG-SAFE-001 support coverage (03 §5.6.0, acceptance ⑨-a)"
        )

    limiter = bootstrap_limiter_rad_s()[joint_index]
    over = tuple(sample for sample in samples if abs(sample.commanded_rad_s) > limiter)
    if over:
        raise SweepPublicationRefusedError(
            f"{len(over)} commanded sample(s) exceed the bootstrap limiter {limiter} rad/s at "
            "joint "
            f"{joint_index}; raising the limiter to match an observation is self-approval, not "
            "a variant (03 §5.6.0, acceptance ⑨-a/⑨-b)"
        )

    tracking = tuple(
        abs(sample.commanded_rad_s - sample.measured_rad_s)
        for sample in samples
        if sample.measured_rad_s is not None
    )
    return SweepPublication(
        joint_index=joint_index,
        limiter_rad_s=limiter,
        commands_over_limiter=0,
        tracking_error_rad_s=tracking,
    )
