"""The guarded torque-ON: authorize -> read present pose -> hold target -> 0xFC.

`02` FR-CON-014 ⑬ engages a present-pose hold with `enable_torque()` (0xFC) and `12`
FR-SAF-075 makes that the one explicit safe-engage. Two properties are the safety, and both
are enforced here before any frame leaves:

Order. The hold target must be read from the present pose immediately before 0xFC, so torque
comes on holding exactly where the arm already is. The arm has no holding brake and the
operator is physically supporting it during bring-up; engaging against any other target
accelerates it out of the operator's hands. Acceptance ③ forbids an arbitrary-target engage
and acceptance ④ bounds the movement the engage itself causes.

Motor set. The engage addresses `backend.endeffector.EndEffectorProfile.motor_send_ids` and
nothing else. Eight ids per arm is the frozen action layout, not an inventory: the fitted
spatula build puts no motor on `0x08`, and a frame addressed to it is never an error return —
nobody ACKs it, the transmit error counter climbs, and the controller falls to ERROR-PASSIVE,
which degrades the seven joints that are present. Measured on this bench: sixteen unanswered
frames took both channels there.

Authorization is two independent gates and neither subsumes the other. `backend.preflight`
answers whether this session on this host is fit to energize — the live RID cross-check, the
side, the CAN-FD link, the writer lock, the clamp canon — and names the precondition that
blocked. The WP-1-05 manifest answers whether the gates that must have PASSed did, with
PG-SAFE-001's evidence hash declared. A session can clear one and fail the other.

The sequence reaches for no CAN handle. It drives a `TorqueEngageBus` — read the present pose
of named motors, enable torque on named motors holding a given frame, drop torque on named
motors — which a real follower's bus satisfies and a recording fake satisfies offline.
Binding it to the real `OaOpenArmFollower` bus and real motors is deferred to a real fixture
(`02a` §4.1); what runs here is the sequence logic and its refusals, proven against the fake.

The hold frame is built by the actuation spine's `positions_to_batch`, so it carries the
spine's hold gains — kp > 0. That is what makes a SAFE_HOLD a gravity-comp hold and not a
torque-0 limp command (`01` §4.1); `assert_safe_hold` re-checks it before 0xFC ever goes out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.actuation import positions_to_batch
from backend.endeffector import EndEffectorProfile
from backend.preflight import PreflightReport, authorize_torque_on
from backend.torque_bringup.hold import assert_safe_hold
from backend.torque_bringup.preconditions import TorqueOnManifest, assert_torque_on_allowed
from backend.torque_bringup.stop_path import assert_stop_path_cuts_no_torque
from contracts.action import ExecutedMitCommand
from contracts.units import Rad


class TorqueEngageSequenceError(RuntimeError):
    """Raised when the guarded torque-ON ordering or target invariant is violated.

    A real raise, never an assert: the difference between engaging on the present pose and
    engaging on an arbitrary target is the difference between a held arm and a jump on a
    brakeless 40 Nm arm.
    """


class FittedMotorMismatchError(RuntimeError):
    """Raised when the engage would address a motor set the fitted tool does not have.

    Distinct from the ordering error because the consequence is distinct: an ordering slip
    jumps the arm, an inventory slip degrades the CAN controller and takes the joints that
    do exist down with it.
    """


class TorqueDisengageRefusedError(RuntimeError):
    """Raised when a disengage is requested without the arm declared supported.

    Dropping torque on a brakeless arm is a fall, not a stop (`12` NFR-SAF-009). The
    refusal is the only thing standing between an operator's disengage and the arm's own
    weight, so it raises rather than warns.
    """


class TorqueEngageBus(Protocol):
    """The bus capability the guarded torque-ON sequence needs.

    Every method takes the motor ids it may address. Passing them rather than letting the
    bus walk its own construction list is the point: `DamiaoMotorsBus` defaults to every
    motor it was built with, which on a spatula build includes an id nothing answers on.

    A real `DamiaoMotorsBus` (via the follower) satisfies this; a recording fake does too.
    Keeping it structural means the sequence depends on the shape rather than importing the
    robot stack — the discipline the actuation spine's `MitBus` keeps.
    """

    def read_present_pose(self, send_ids: tuple[int, ...]) -> tuple[Rad, ...]:
        """Read the current angle of each named motor, in radians, in the given id order."""
        ...

    def enable_torque(
        self, send_ids: tuple[int, ...], hold_batch: tuple[ExecutedMitCommand, ...]
    ) -> None:
        """Enable torque (0xFC) on the named motors holding the given present-pose frame.

        The implementor owns the atomicity: between 0xFC and the first MIT frame a motor
        holds nothing, so the enable and the hold frame must not be separated by a caller.
        """
        ...

    def drop_torque(self, send_ids: tuple[int, ...]) -> None:
        """Drop torque (0xFD) on the named motors, ending the hold."""
        ...


@dataclass(frozen=True)
class EngageResult:
    """The record a guarded torque-ON produced, for the audit and the bounce check.

    Attributes:
        send_ids: The motor ids the engage addressed — the fitted set, in bus order.
        present: The present pose read immediately before 0xFC, radians per fitted motor.
        hold_batch: The MIT position-hold frame engaged — one command per fitted motor,
            built from `present` with the spine's hold gains.
    """

    send_ids: tuple[int, ...]
    present: tuple[Rad, ...]
    hold_batch: tuple[ExecutedMitCommand, ...]

    def commanded_displacement_rad(self) -> tuple[float, ...]:
        """Per-joint difference between the engaged hold target and the present pose.

        A guarded engage holds exactly where the arm is, so every entry is 0.0. This is the
        offline half of acceptance ④; the physical joint movement on real motors is deferred
        to a real fixture.

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


def assert_targets_are_present_pose(
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


def assert_pose_covers_fitted_motors(present: tuple[Rad, ...], send_ids: tuple[int, ...]) -> None:
    """Refuse a present-pose read whose width is not the fitted motor count.

    A wider read means the bus addressed a motor the fitted tool does not carry, which is
    what walks the controller to ERROR-PASSIVE; a narrower one means a fitted joint went
    unread and would be energized against an angle nobody measured.

    Args:
        present: The pose the bus returned.
        send_ids: The fitted motor ids the read was asked for.

    Raises:
        FittedMotorMismatchError: On any width other than the fitted motor count.
    """
    if len(present) == len(send_ids):
        return
    if len(present) > len(send_ids):
        consequence = (
            "a wider read addressed a motor that is not on this bus, and an unanswered frame "
            "walks the controller to ERROR-PASSIVE and degrades the joints that are present"
        )
    else:
        consequence = (
            "a narrower read left a fitted joint unmeasured, and 0xFC would energize it "
            "against an angle nobody read"
        )
    addressed = ", ".join(f"{send_id:#04x}" for send_id in send_ids)
    raise FittedMotorMismatchError(
        f"present pose is {len(present)} wide for {len(send_ids)} fitted motors "
        f"({addressed}); {consequence}"
    )


class GuardedTorqueOn:
    """One guarded torque-ON session, and its reversal.

    Ownership: holds the bus, the fitted end-effector profile, the preflight report and the
    startup manifest for one session. It engages at most once; the order of bus calls it
    makes is what acceptance ③ reads, and every invariant clears before the 0xFC leaves.

    Threading: single-threaded operator flow. `torque_may_be_live` is set before the bus
    call rather than after, so a bus that raises mid-engage still leaves a session that
    knows torque may be on and can be told to drop it.
    """

    def __init__(
        self,
        bus: TorqueEngageBus,
        end_effector: EndEffectorProfile,
        preflight: PreflightReport,
        manifest: TorqueOnManifest,
    ) -> None:
        """Bind a session to its bus, its fitted tool, and its two authorizations.

        Args:
            bus: The bus the engage drives.
            end_effector: The tool fitted to this arm; decides which motors are addressed.
            preflight: The five-precondition report `may_enable_torque` is read from.
            manifest: The four-precondition startup manifest torque-ON is admitted against.
        """
        self._bus = bus
        self._end_effector = end_effector
        self._preflight = preflight
        self._manifest = manifest
        self._engaged = False
        self._torque_may_be_live = False

    @property
    def engaged(self) -> bool:
        """Whether this session completed an engage.

        Returns:
            (bool) True once `engage` returned.
        """
        return self._engaged

    @property
    def torque_may_be_live(self) -> bool:
        """Whether torque may currently be on, including after a failed engage.

        Returns:
            (bool) True from the moment 0xFC was attempted until a disengage returns.
        """
        return self._torque_may_be_live

    @property
    def send_ids(self) -> tuple[int, ...]:
        """The motor ids this session may address — the fitted set, never a fixed eight.

        Returns:
            (tuple[int, ...]) The fitted tool's CAN send ids.
        """
        return self._end_effector.motor_send_ids

    def engage(self) -> EngageResult:
        """Run the guarded torque-ON sequence and return its record.

        The order is fixed and enforced: authorize against both gates, prove the stop path
        cuts no torque, read the present pose of the fitted motors, build the present-pose
        hold (kp > 0), refuse any non-present target, then enable torque. Nothing reads a
        pose before the authorizations clear, and no 0xFC goes out before the present pose
        is read.

        Returns:
            (EngageResult) The ids addressed, the present pose read, and the frame engaged.

        Raises:
            TorqueOnBlockedError: If any of the five preflight preconditions failed; the
                message names each one and its evidence.
            TorqueOnRefusedError: If any mandatory manifest precondition is missing or not
                PASS.
            TorqueCutOnStopPathError: If a torque cut is reachable from the stop path.
            FittedMotorMismatchError: If no motor is fitted, or the present-pose read is not
                the fitted motor count wide.
            TorqueEngageSequenceError: If already engaged, or the hold target is not the
                present pose.
            SafeHoldViolationError: If the hold frame is a torque-0 command (kp <= 0).
        """
        if self._engaged:
            raise TorqueEngageSequenceError(
                "torque-ON already engaged this session; a second engage would re-power on a "
                "possibly-moved pose"
            )
        authorize_torque_on(self._preflight)
        assert_torque_on_allowed(self._manifest)
        assert_stop_path_cuts_no_torque()

        send_ids = self.send_ids
        if not send_ids:
            raise FittedMotorMismatchError(
                f"the fitted {self._end_effector.tool_id} tool declares no motors; there is "
                "nothing to engage and a zero-width frame would be sent to the bus"
            )

        present = self._bus.read_present_pose(send_ids)
        assert_pose_covers_fitted_motors(present, send_ids)
        hold_batch = build_present_pose_hold(present)
        assert_targets_are_present_pose(hold_batch, present)

        self._torque_may_be_live = True
        self._bus.enable_torque(send_ids, hold_batch)
        self._engaged = True
        return EngageResult(send_ids=send_ids, present=present, hold_batch=hold_batch)

    def disengage(self, arm_supported: bool) -> tuple[int, ...]:
        """Drop torque on the fitted motors, ending the hold.

        Not the stop path. A stop is a Cat-2 hold frame; this is an operator deliberately
        ending the session, and it is admitted only once the operator declares the arm is
        mechanically supported, because with no holding brake the arm falls the instant
        torque goes.

        It is never refused for being un-engaged. A bus that raised after 0xFC left leaves
        torque on with `engaged` still false, and refusing there would strand the operator
        with a live arm and no way to release it.

        Args:
            arm_supported: Whether the arm is mechanically supported or held right now.

        Returns:
            (tuple[int, ...]) The motor ids the drop addressed.

        Raises:
            TorqueDisengageRefusedError: If the arm is not declared supported.
        """
        if not arm_supported:
            raise TorqueDisengageRefusedError(
                "disengage refused: the arm is not declared supported. This arm has no "
                "holding brake, so dropping torque lets it fall under its own weight and the "
                "end effector's (12 NFR-SAF-009); support the arm, then disengage"
            )
        send_ids = self.send_ids
        self._bus.drop_torque(send_ids)
        self._engaged = False
        self._torque_may_be_live = False
        return send_ids
