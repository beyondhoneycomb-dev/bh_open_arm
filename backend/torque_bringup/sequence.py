"""The guarded torque-ON sequence: present-pose read -> hold target -> 0xFC engage.

`02` FR-CON-014 ⑬ engages a present-pose hold with `enable_torque()` (0xFC), and `12`
FR-SAF-075 makes that the one explicit safe-engage. The order is the safety property:
the hold target must be *read from the present pose* immediately before 0xFC, so torque
comes on holding exactly where the arm already is. Engaging against any other target is a
commanded jump on power-up — acceptance ③ forbids it ("임의 타깃으로 인게이지 0건"), and
acceptance ④ requires the engage to move the arm no further than an allowed window.

The sequence never reaches for a CAN handle itself. It drives a `TorqueEngageBus` — the
one capability it needs: read the present joint angles, and engage a MIT position-hold
frame under 0xFC. A real follower's bus satisfies it; the offline tests drive a recording
fake. Binding this to the real `OaOpenArmFollower` bus and the real motors is deferred to
a real fixture (`02a` §4.1); what runs here is the sequence logic and its ordering, proven
against the fake.

The hold frame is built by the actuation spine's `positions_to_batch`, so it carries the
spine's hold gains — kp > 0. That is what makes a SAFE_HOLD a gravity-comp hold and not a
torque-0 limp command (`01` §4.1); `assert_safe_hold` re-checks it before 0xFC ever goes
out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.actuation import positions_to_batch
from backend.torque_bringup.hold import assert_safe_hold
from backend.torque_bringup.preconditions import TorqueOnManifest, assert_torque_on_allowed
from contracts.action import ExecutedMitCommand
from contracts.units import Rad


class TorqueEngageSequenceError(RuntimeError):
    """Raised when the guarded torque-ON ordering or target invariant is violated.

    A real raise, never an assert: the difference between engaging on the present pose
    and engaging on an arbitrary target is the difference between a held arm and a jump
    on a brakeless 40 Nm arm.
    """


class TorqueEngageBus(Protocol):
    """The one bus capability the guarded torque-ON sequence needs.

    A real `DamiaoMotorsBus` (via the follower) satisfies it; a recording fake does too.
    Keeping it structural means the sequence depends on the shape, not on importing the
    robot stack — the same discipline the actuation spine's `MitBus` keeps.
    """

    def read_present_pose(self) -> tuple[Rad, ...]:
        """Read the current joint angles, in radians, one per motor."""
        ...

    def engage_hold(self, hold_batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Enable torque (0xFC) holding the given present-pose MIT frame."""
        ...


@dataclass(frozen=True)
class EngageResult:
    """The record a guarded torque-ON produced, for the audit and the bounce check.

    Attributes:
        present: The present pose read immediately before 0xFC, radians per joint.
        hold_batch: The MIT position-hold frame engaged — one command per joint, built
            from `present` with the spine's hold gains.
    """

    present: tuple[Rad, ...]
    hold_batch: tuple[ExecutedMitCommand, ...]

    def commanded_displacement_rad(self) -> tuple[float, ...]:
        """Per-joint difference between the engaged hold target and the present pose.

        A guarded engage holds exactly where the arm is, so every entry is 0.0. This is
        the offline half of acceptance ④; the *physical* joint movement on real motors is
        deferred to a real fixture.

        Returns:
            (tuple[float, ...]) `hold_target - present` per joint, radians.
        """
        return tuple(
            command.q.value - present.value
            for command, present in zip(self.hold_batch, self.present, strict=True)
        )


def build_present_pose_hold(present: tuple[Rad, ...]) -> tuple[ExecutedMitCommand, ...]:
    """Build the MIT position-hold frame that holds exactly at the present pose.

    The frame carries the actuation spine's hold gains (kp > 0), so it is a gravity-comp
    hold and not a torque-0 command; `assert_safe_hold` verifies that before it is used.

    Args:
        present: The present joint pose, radians per joint.

    Returns:
        (tuple[ExecutedMitCommand, ...]) The present-pose hold frame.
    """
    hold_batch = positions_to_batch(present)
    assert_safe_hold(hold_batch)
    return hold_batch


def _assert_targets_are_present_pose(
    hold_batch: tuple[ExecutedMitCommand, ...], present: tuple[Rad, ...]
) -> None:
    """Refuse a hold whose targets are not exactly the present pose (acceptance ③).

    Args:
        hold_batch: The MIT frame about to be engaged.
        present: The present pose it must hold at.

    Raises:
        TorqueEngageSequenceError: If any joint's hold target differs from its present
            angle — engaging on an arbitrary target is a commanded jump.
    """
    if len(hold_batch) != len(present):
        raise TorqueEngageSequenceError(
            f"hold frame width {len(hold_batch)} does not match present pose width {len(present)}"
        )
    for index, (command, angle) in enumerate(zip(hold_batch, present, strict=True)):
        if command.q != angle:
            raise TorqueEngageSequenceError(
                f"joint {index}: hold target {command.q} is not the present pose {angle}; "
                "torque-ON must engage the present pose, never an arbitrary target "
                "(02 FR-CON-014 ⑬, acceptance ③)"
            )


class GuardedTorqueOn:
    """A single guarded torque-ON: preconditions -> present read -> hold target -> 0xFC.

    Ownership: holds the `TorqueEngageBus` and the startup manifest for one session. It
    engages at most once; the order of bus calls it makes is the ordering acceptance ③
    reads, and it enforces every invariant before the 0xFC ever leaves.
    """

    def __init__(self, bus: TorqueEngageBus, manifest: TorqueOnManifest) -> None:
        """Bind a session to its bus and its startup manifest.

        Args:
            bus: The bus the engage drives.
            manifest: The four-precondition startup manifest torque-ON is admitted against.
        """
        self._bus = bus
        self._manifest = manifest
        self._engaged = False

    @property
    def engaged(self) -> bool:
        """Whether this session has already engaged torque.

        Returns:
            (bool) True once `engage` has run.
        """
        return self._engaged

    def engage(self) -> EngageResult:
        """Run the guarded torque-ON sequence and return its record.

        The order is fixed and enforced: admit the four preconditions, read the present
        pose, build the present-pose hold (kp > 0), refuse any non-present target, then
        engage 0xFC. Nothing reads a target before the preconditions clear, and no 0xFC
        goes out before the present pose is read.

        Returns:
            (EngageResult) The present pose read and the hold frame engaged.

        Raises:
            TorqueOnRefusedError: If any mandatory precondition is missing or not PASS.
            TorqueEngageSequenceError: If already engaged, or the hold target is not the
                present pose.
            SafeHoldViolationError: If the hold frame is a torque-0 command (kp <= 0).
        """
        if self._engaged:
            raise TorqueEngageSequenceError(
                "torque-ON already engaged this session; a second engage would re-power on a "
                "possibly-moved pose"
            )
        assert_torque_on_allowed(self._manifest)
        present = self._bus.read_present_pose()
        hold_batch = build_present_pose_hold(present)
        _assert_targets_are_present_pose(hold_batch, present)
        self._bus.engage_hold(hold_batch)
        self._engaged = True
        return EngageResult(present=present, hold_batch=hold_batch)
