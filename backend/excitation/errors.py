"""The refusal errors of the exciting-trajectory harness (`WP-2B-06`).

Each error is a hard block the caller cannot read as success. The contract (`02b`
§2.3) makes injection a torque-ON path on a 40 Nm brakeless arm, so every
precondition the harness fails is an explicit exception rather than a silent
no-op: a missing torque path, an un-armed dry-run gate, an unconfirmed safe state,
or a resume attempted while the safety latch is still held. An over-limit
excitation spec is refused here too, before any of it can be commanded.
"""

from __future__ import annotations


class ExcitationError(RuntimeError):
    """Base of every exciting-trajectory refusal, so a caller can catch the family."""


class TorquePathUnavailableError(ExcitationError):
    """Raised when injection is attempted without an `FR-MOT-058` torque command path.

    `02b` §2.3 ④: without the torque command path there is no way to apply the
    identification torque, so injection cannot start — it waits. This is the runtime
    face of that "cannot start" state, not a degraded partial run.
    """

    def __init__(self) -> None:
        """Build the error naming the missing torque path."""
        super().__init__(
            "exciting trajectory cannot start: no FR-MOT-058 torque command path is "
            "wired, so the identification torque cannot be applied (02b §2.3 WP-2B-06 ④)"
        )


class DryRunGateNotArmedError(ExcitationError):
    """Raised when injection is attempted before the `WP-2A-00` dry-run gate has armed.

    `02b` §2.3: the exciting trajectory requires the dry-run hard-gate to pass. The
    harness consumes an armed `RealSendBarrier`; an un-armed one means no dry-run has
    cleared this trajectory and real transmission is forbidden.
    """

    def __init__(self) -> None:
        """Build the error naming the un-armed dry-run gate."""
        super().__init__(
            "exciting trajectory cannot start: the WP-2A-00 dry-run hard-gate has not "
            "armed, so real transmission of the identification trajectory is forbidden "
            "(02b §2.3 WP-2B-06)"
        )


class UnsafeInitialStateError(ExcitationError):
    """Raised when injection is attempted before the safe initial state is confirmed.

    `02b` §2.3 ①: injection starts only after the rest pose, drop-zone isolation, and
    mechanical support are confirmed. A missing or incomplete confirmation is refused,
    because the first commanded torque on a brakeless arm assumes the arm is supported.
    """

    def __init__(self, reason: str) -> None:
        """Build the error naming which part of the safe initial state was not met.

        Args:
            reason: The specific unmet condition (unconfirmed flag or out-of-range pose).
        """
        super().__init__(
            f"exciting trajectory cannot start: safe initial state not confirmed — {reason} "
            f"(02b §2.3 WP-2B-06 ①)"
        )


class LatchStillEngagedError(ExcitationError):
    """Raised when a resume is attempted while the safety latch from an abort is still held.

    An abort engages the shared one-way `SafetyLatch`, and the only exit is an operator
    acknowledgement (`12` FR-SAF-028/043). Resuming while it is still held would be the
    auto-resume the latch exists to prevent, so the resume is refused until the operator
    has cleared it and re-confirmed the safe state.
    """

    def __init__(self) -> None:
        """Build the error naming the still-engaged latch."""
        super().__init__(
            "cannot resume injection: the safety latch engaged by the abort is still held; "
            "an operator must acknowledge it and re-confirm the safe state before resume "
            "(12 FR-SAF-043)"
        )


class TrajectoryLimitError(ExcitationError):
    """Raised when an excitation spec would drive a joint past its position or velocity bound.

    The excitation amplitude and band together fix a peak position excursion and a peak
    velocity; a spec whose peaks leave the joint's bounds is refused at construction, so
    an out-of-range trajectory can never reach the injection loop.
    """
