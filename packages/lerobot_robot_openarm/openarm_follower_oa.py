"""The hardware OpenArm follower: torque-OFF bring-up + explicit zero (WP-1-02).

`OaOpenArmFollower` subclasses LeRobot's `OpenArmFollower` (11 NFR-INF-008 wants the
single enforcement point to be a subclass that overrides `OpenArmFollower.send_action`;
WP-1-03 adds that override to THIS file under the sequential ownership handover). What
WP-1-02 owns is the SAFE bring-up and the explicit zero flow:

- `connect_readonly()` opens the bus, registers motors, and warms the feedback cache —
  and nothing else. `enable_torque`/`enable_all` are never called on this path, so
  after it torque is OFF (12 FR-SAF-075, 02 FR-CON-062). This class defines no
  torque-ON path at all; guarded torque-ON is WP-1-05's, after PG-SAFE-001.
- `connect()` is overridden to drop the stock follower's auto `set_zero_position()` and
  `enable_torque()` (02 FR-CON-061): connecting is torque-OFF and never zeroes as a
  side effect. It delegates to `connect_readonly()`.
- `set_zero()` is the explicit operator flow (02 FR-CON-063): it refuses while torque
  is enabled (the motor silently ignores 0xFE when enabled, so disable-first is
  mandatory), disables, settles, emits the ONE 0xFE in the codebase, reads the raw
  angles back, verifies the residual against the URDF-zero reference, and persists the
  calibration atomically. `0xAA` flash-store is never emitted (firmware-unreliable).

The joint zero lives in motor NV (written by 0xFE), not on disk; the disk JSON is the
SoT for signs, scale, gripper endpoints, and the residual witness (16 M-1, CTR-CAL@v1).
The bus is injectable so the whole flow runs against a fixture with no CAN present; the
hardware acceptances (torque-OFF on 16 motors, readback residual, power-cycle
persistence) are deferred to a real fixture and re-verified at `RESUME-1-02-ZERO`.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from pathlib import Path

from lerobot.motors.damiao import DamiaoMotorsBus
from lerobot.robots.openarm_follower import OpenArmFollower
from lerobot.robots.openarm_follower.config_openarm_follower import (
    LEFT_DEFAULT_JOINTS_LIMITS,
    RIGHT_DEFAULT_JOINTS_LIMITS,
    OpenArmFollowerConfig,
)
from lerobot.robots.robot import RobotAction, RobotObservation

from backend.actuation import (
    AcceptedTargetPublisher,
    ActionStreamWatchdog,
    ActuationGateway,
    Clock,
    CollisionGuard,
    DropCounter,
    GateResult,
    SafetyFilter,
    SafetyLimits,
    WallClock,
)
from backend.actuation.config import FRESHNESS_WINDOW_SEC, MIT_HOLD_KD, MIT_HOLD_KP
from backend.calibration.atomic_io import (
    calibration_path_for,
    load_calibration,
    save_calibration_atomic,
)
from backend.calibration.schema import (
    DEFAULT_JOINT_SCALE,
    DEFAULT_JOINT_SIGN,
    MOTOR_COUNT,
    MOTOR_ORDER,
    CalibrationError,
    OpenArmCalibration,
    ZeroMethod,
)
from backend.calibration.verify import ResidualResult, compute_residual
from backend.can.lock import LockManager, guarded_connect
from backend.endeffector import EndEffectorProfile, default_profile
from backend.threshold.constants import JOINT_EFFORT_LIMITS_NM
from contracts.action import DROP_COUNTER_META
from contracts.plugin.config import Side
from contracts.plugin.robot_abc import OpenArmRobot
from contracts.units import Deg, Nm
from ops.cancel.scheduler import LatchReason
from packages.lerobot_robot_openarm.config_oa import (
    BI_OA_FOLLOWER_TYPE,
    OA_FOLLOWER_TYPE,
    BiOaOpenArmFollowerConfig,
    OaOpenArmFollowerConfig,
)

# CAN interface name per arm. These are the socketcan defaults; the authoritative
# fixed interface names come from the CAN-hygiene wave (WP-0B-05) and are confirmed at
# hardware bring-up. The value is only read when the bus is actually opened (deferred),
# so a placeholder here never affects the offline flow. A caller that has the operator's
# persisted role-to-channel answer passes it as `port` instead: the two arms are
# indistinguishable by CAN id (03 §2.1), so this map is a placeholder and never evidence.
PORT_BY_SIDE = {"left": "can0", "right": "can1"}
_DEFAULT_PORT = "can0"

# Seconds to let the arm settle after disabling torque before emitting 0xFE, so the
# zero is captured on a mechanically-still arm rather than mid-sag (02 FR-CON-063).
SET_ZERO_SETTLE_SEC = 0.2

# Gripper endpoint seeds (radians). v2 pinch is a revolute joint over −45°..0° with no
# load cell, so the real endpoints are captured by hand (16 D-5); these are only the
# pre-capture defaults, and their `captured` flags stay False until a hand capture.
# The gripper's slot name in the frozen MOTOR_ORDER layout. The slot is always present; the
# motor behind it is not, which is why zeroing filters on it rather than assuming eight.
GRIPPER_MOTOR_NAME = MOTOR_ORDER[-1]

GRIPPER_OPEN_DEFAULT_RAD = 0.0
GRIPPER_CLOSE_DEFAULT_RAD = math.radians(-45.0)

# Physical Peak Torque per motor, newton-metres (03 FR-MOT-037): J1/J2 (DM8009) 40,
# J3/J4 (DM4340) 27; J5-J7 and the gripper (DM4310) 10 (10 §2.3). This is the axis a
# torque clamp uses — never the packet-scale T_MAX (DM8009 54 / DM4340 28 / DM4310 10),
# which is wider on the shoulders and would admit a shoulder over-torque if used as the
# clamp bound. The operational torque bound defaults to the peak (a valid subset).
PEAK_TORQUE_NM = (40.0, 40.0, 27.0, 27.0, 10.0, 10.0, 10.0, 10.0)

# Per-joint feed-forward torque band the command path refuses outside, newton-metres, in
# MOTOR_ORDER. The seven arm joints take the URDF effort figures, the same array that ceilings
# a collision threshold, so one number bounds the torque a joint may be commanded and the
# torque a joint may be judged by. The gripper slot is None rather than a figure: the URDF
# declares no effort for joint8 and `03` FR-MOT-047 forbids expressing grip force in Nm at all,
# so there is no band to be inside and every non-zero value on that slot is refused.
#
# On J5-J7 this band (7) is tighter than PEAK_TORQUE_NM (10), so a torque this path admits is
# already inside the gateway's Peak-Torque clamp and that clamp never alters an accepted value.
# The two are not redundant: refusal is what a command path owes a caller, clamping is what a
# proposal generator owes one, and a clamp on a command path would send a torque nobody asked
# for (`backend/threshold_calib/settings.py` states the same split for thresholds).
FEEDFORWARD_TORQUE_LIMIT_NM: tuple[float | None, ...] = (*JOINT_EFFORT_LIMITS_NM, None)

# What a slot carries when the caller asked for no feed-forward torque on it.
NO_FEEDFORWARD_TORQUE_NM = 0.0

# Per-joint velocity ceiling, rad/s (12 §2.5 ARM_JOINT_VELOCITY_LIMITS_RAD_S for the
# seven arm joints; the gripper reuses the wrist ceiling as a conservative bootstrap
# pending a hand capture — a real-fixture re-verification hook). Independent of the
# step-delta guard: velocity is |Δq|/dt, the jump guard is |Δq| per step (14 FR-OPS-012).
VELOCITY_LIMIT_RAD_S = (1.57, 1.57, 3.14, 3.14, 12.6, 12.6, 12.6, 12.6)

# Per-joint step-delta jump guard, radians per step (03 FR-MOT-036
# `joint_delta_position_limits`). NOT a velocity limit — a separate parameter. The
# YAML's `rad/s` comment is a typo; at 50 Hz a 1.8 rad/step delta is 90 rad/s, so a
# delta guard alone leaves velocity unbounded, which is why velocity is checked apart.
STEP_DELTA_LIMIT_RAD = (1.8, 1.8, 3.3, 2.3, 3.5, 3.5, 3.5, 3.5)

# Acceleration and jerk ceilings are derived from the velocity limit by a ramp time,
# because the spec fixes no hardware acceleration/jerk figure — FR-SYS-017 requires
# the guards to exist, and their authoritative values come from the rig (PG-VEL-001).
# These are conservative bootstrap values, kept as their own parameters, never merged
# with velocity or with each other.
ACCEL_RAMP_SEC = 0.1
JERK_RAMP_SEC = 0.1
ACCEL_LIMIT_RAD_S2 = tuple(velocity / ACCEL_RAMP_SEC for velocity in VELOCITY_LIMIT_RAD_S)
JERK_LIMIT_RAD_S3 = tuple(accel / JERK_RAMP_SEC for accel in ACCEL_LIMIT_RAD_S2)

# The control period the rate checks divide by, seconds. A bootstrap loop rate; the
# authoritative f_max is measured at PG-RT-001a (WP-1-04), not fixed here.
CONTROL_PERIOD_SEC = 0.02

# Age past which a source is stale — and so the interval of silence past which the action
# stream counts as interrupted (`03` FR-MOT-058 ②). Bound to the actuation spine's own window
# rather than restated as a number, so the age this path judges and the age the scheduler tick
# calls a STALE_SOURCE_HOLD (`backend.actuation.decider.decide`) cannot drift apart. The two
# constants meet a relation neither of them states alone — a stream keeping its declared period
# is never stale, one missing three consecutive periods always is — and
# `tests/wp103/test_torque_watchdog.py` is where that relation is held rather than asserted.
GATEWAY_FRESHNESS_WINDOW_SEC = FRESHNESS_WINDOW_SEC

# The side prefixes the bimanual splits every per-motor argument on. A key carrying neither
# reaches no arm at all.
SIDE_PREFIXES = ("left", "right")


def _mechanical_limits_for_side(side: str) -> dict[str, tuple[float, float]]:
    """Return the mechanical URDF joint limits (degrees) for an arm side.

    Args:
        side: "left" or "right"; the side-dependent shoulder-lift limit differs.

    Returns:
        (dict[str, tuple[float, float]]) Per-motor `(low, high)` degree limits.
    """
    source = RIGHT_DEFAULT_JOINTS_LIMITS if side == "right" else LEFT_DEFAULT_JOINTS_LIMITS
    return {str(motor): (float(low), float(high)) for motor, (low, high) in source.items()}


def build_safety_limits(side: str) -> SafetyLimits:
    """Build the arm's safety envelope from its side limits and the physical constants.

    The operational limits default to the mechanical limits (a valid subset — equality
    is contained): the two-stage clamp (`03` FR-MOT-030) admits a tighter operational
    envelope, and that tightening is later tuning, not a bootstrap default. The torque
    bound defaults to the physical peak, so a clamp is Peak-Torque-based (`03`
    FR-MOT-037), and the three rate guards are supplied as independent parameters.

    Args:
        side: The arm side, "left" or "right".

    Returns:
        (SafetyLimits) The validated safety envelope for the arm.
    """
    mechanical = _mechanical_limits_for_side(side)
    mech = tuple((Deg(mechanical[motor][0]), Deg(mechanical[motor][1])) for motor in MOTOR_ORDER)
    return SafetyLimits(
        mechanical_deg=mech,
        operational_deg=mech,
        velocity_limit_rad_s=VELOCITY_LIMIT_RAD_S,
        accel_limit_rad_s2=ACCEL_LIMIT_RAD_S2,
        jerk_limit_rad_s3=JERK_LIMIT_RAD_S3,
        step_delta_limit_rad=STEP_DELTA_LIMIT_RAD,
        peak_torque_nm=tuple(Nm(torque) for torque in PEAK_TORQUE_NM),
        operational_torque_nm=tuple(Nm(torque) for torque in PEAK_TORQUE_NM),
    )


def _utc_now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


class SessionError(RuntimeError):
    """Raised when the connect-once-per-session contract is violated (01 FR-SYS-001).

    Also raised when a flow that requires an open read-only connection is entered
    before `connect_readonly()`.
    """


class TorqueRefusedError(ValueError):
    """Raised when a commanded feed-forward torque leaves the band its joint admits.

    Refused and not clamped. A clamp on a command path sends a torque the caller never asked
    for, so an over-command reaches a 40 Nm brakeless arm as a quieter one instead of as a
    stop; the caller is the only party that can decide what a bounded command should have been.
    """


class GainRefusedError(ValueError):
    """Raised when a commanded MIT gain names a motor no arm carries.

    Refused and not dropped. An unrecognised gain key leaves its joint on the hold gains,
    so a caller asking for a compliant joint would silently get a stiff one — and stiffness
    is the axis on which a mistake is a fight with the operator's hand rather than a slower
    move.
    """


class PartialConnectionError(RuntimeError):
    """Raised when a bimanual follower comes up with only one arm connected (01 §4.2 T1).

    The other arm's connection is torn down before this is raised: a half-connected
    pair must not be left running, and the surviving connection is not left orphaned.
    """


class OaOpenArmFollower(OpenArmFollower):
    """One hardware OpenArm follower arm: torque-OFF bring-up (WP-1-02) + the gateway (WP-1-03).

    WP-1-03 adds the single, un-bypassable action gateway (`11` NFR-INF-008): the
    `send_action` override is the sole enforcement point, and it delegates to an
    `ActuationGateway` that runs the ordered safety filter before any command becomes
    a target. This class never reaches for a CAN write itself — the accepted command
    is written by the scheduler tick, the single writer (`02a` §3.1 ①) — so no
    `robot.bus` write path exists outside the gateway (acceptance ①).

    Ownership: owns its `DamiaoMotorsBus` (`self.bus`, injectable for fixtures), the
    on-disk CTR-CAL@v1 calibration for this instance id, its `ActuationGateway` (built
    lazily, injectable for fixtures), and a `DropCounter` surfacing the CAN packet-drop
    count. Torque state is tracked in `_torque_enabled`; this class never sets it True
    — guarded torque-ON is WP-1-05, after `PG-SAFE-001`.

    The `AcceptedTargetPublisher` is borrowed, not owned: the scheduler's mailbox and clock
    belong to the torque-ON session that stood the spine up, and both arms of a pair offer
    into the same publisher so one bimanual target is assembled from two decisions.
    """

    name = OA_FOLLOWER_TYPE
    config_class = OaOpenArmFollowerConfig

    def __init__(
        self,
        config: OaOpenArmFollowerConfig,
        bus: DamiaoMotorsBus | None = None,
        gateway: ActuationGateway | None = None,
        drop_counter: DropCounter | None = None,
        end_effector: EndEffectorProfile | None = None,
        clock: Clock | None = None,
        publisher: AcceptedTargetPublisher | None = None,
        port: str | None = None,
    ) -> None:
        """Construct the follower without opening any bus.

        Args:
            config: The plugin config; `side` is required (validated by the config).
            bus: An optional bus to use instead of building the real `DamiaoMotorsBus`
                — the seam fixtures use to exercise the flow with no CAN present.
            gateway: An optional pre-built enforcement gateway (a fixture injects one
                over a fake CAN writer); built lazily from this arm's side otherwise.
            drop_counter: An optional CAN packet-drop counter; a fresh one otherwise.
            end_effector: Which tool this arm carries. Decides whether the gripper motor is
                addressed at all; defaults to the no-gripper build, because addressing a motor
                that is not on the bus walks the controller to ERROR-PASSIVE and degrades the
                joints that are.
            clock: The monotonic source the action-stream watchdog and the collision guard
                read; the live wall clock otherwise. A fixture passes a `ManualClock` so an
                elapsed interval is a stated fact rather than a race against the test runner.
            publisher: The publisher carrying each accepted decision onto the scheduler's
                mailbox, shared with the other arm of the pair. Omitted, `send_action` still
                filters and still returns the accepted action, but nothing reaches the single
                writer and no joint is commanded — which is what an arm built outside a
                torque-ON session is.
            port: The CAN interface this arm opens on. Given by a caller holding the
                operator's persisted role-to-channel answer; `PORT_BY_SIDE` otherwise, which
                is a placeholder rather than an identification — the arms answer on the same
                CAN ids and the adapter has been seen at two different USB port paths.
        """
        self._end_effector = end_effector if end_effector is not None else default_profile()
        self._clock = clock if clock is not None else WallClock()
        self._plugin_config = config
        super().__init__(self._build_hardware_config(config, port))
        if bus is not None:
            self.bus = bus
        self._torque_enabled = False
        self._connected_readonly = False
        self._connect_count = 0
        self._calibration = self._load_oa_calibration()
        self._gateway = gateway
        self._drop_counter = drop_counter if drop_counter is not None else DropCounter()
        self._last_gate_result: GateResult | None = None
        self._last_latch_reason: LatchReason | None = None
        self._watchdog = ActionStreamWatchdog(self._clock)
        self._publisher = publisher

    def _build_hardware_config(
        self, config: OaOpenArmFollowerConfig, port: str | None
    ) -> OpenArmFollowerConfig:
        """Build the full LeRobot hardware config from the minimal plugin config.

        The plugin config carries only `side` and the velocity/torque switch (the
        frozen CTR-PLUG@v1 surface); the CAN and motor hardware fields come from
        LeRobot's follower defaults. The port is the caller's when they have the
        operator's channel record, and the side-derived placeholder otherwise — that
        placeholder is also what the lock check reads, so the two cannot be given
        different answers.

        Args:
            config: The plugin config.
            port: The CAN interface to open on, or None for the side placeholder.

        Returns:
            (OpenArmFollowerConfig) The full hardware config.

        Raises:
            SessionError: If the config has no side (the config layer should have
                already refused this).
        """
        if config.side is None:
            raise SessionError("OaOpenArmFollower requires a side; the config must set left|right")
        side_str = config.side.value
        hardware = OpenArmFollowerConfig(
            id=config.id,
            calibration_dir=config.calibration_dir,
            port=port if port is not None else PORT_BY_SIDE.get(side_str, _DEFAULT_PORT),
            side=side_str,
            use_velocity_and_torque=config.use_velocity_and_torque,
        )
        hardware.motor_config = self._fitted_motor_config(hardware.motor_config)
        return hardware

    def _fitted_motor_config(
        self, full: dict[str, tuple[int, int, str]]
    ) -> dict[str, tuple[int, int, str]]:
        """Narrow the follower's motor table to the ids the fitted tool actually carries.

        `DamiaoMotorsBus.connect` handshakes every motor it was registered with, so the
        registered set is not a convenience — it is what the bus demands answer before it will
        open. A tool-less arm registered with the stock table waits on a gripper that is not
        bolted on and the whole connect fails; an arm whose table was narrowed past the fitted
        set comes up a joint short and nothing downstream notices.

        Keyed on send id rather than motor name: the profile's authority is `motor_send_ids`,
        and a name-keyed filter would agree with a table whose names drifted.

        Args:
            full: The stock follower's motor table, name to (send id, recv id, type).

        Returns:
            (dict) The same entries for the fitted ids only, in the profile's id order.

        Raises:
            SessionError: If the profile declares a send id the table has no entry for. Dropping
                it silently is what turns a typo into an arm that comes up missing a joint.
        """
        entry_by_send_id = {spec[0]: (name, spec) for name, spec in full.items()}
        fitted = tuple(self._end_effector.motor_send_ids)
        unknown = [send_id for send_id in fitted if send_id not in entry_by_send_id]
        if unknown:
            missing = ", ".join(f"{send_id:#04x}" for send_id in unknown)
            known = ", ".join(f"{send_id:#04x}" for send_id in entry_by_send_id)
            raise SessionError(
                f"the fitted tool declares motor id(s) {missing}, which the follower's motor "
                f"table does not carry (it has {known}); registering the rest anyway would open "
                "the bus one joint short of what is bolted on"
            )
        return dict(entry_by_send_id[send_id] for send_id in fitted)

    @property
    def side(self) -> str:
        """The arm side as a string ("left" or "right")."""
        return str(self.config.side)

    @property
    def is_torque_enabled(self) -> bool:
        """Whether motor torque is currently enabled.

        WP-1-02 never enables torque, so this is False across the whole bring-up; the
        read-only measurement (WP-1-04) and the guarded torque-ON (WP-1-05) read it.
        """
        return self._torque_enabled

    @property
    def is_calibrated(self) -> bool:
        """Whether a completed set-zero calibration exists for this instance.

        Overrides the stock follower's motor-NV check: the SoT for "has this arm been
        zeroed" is the disk calibration with a recorded `last_zero_at` (CTR-CAL@v1).
        """
        return self._calibration is not None and self._calibration.last_zero_at is not None

    @property
    def calibration_model(self) -> OpenArmCalibration | None:
        """The loaded CTR-CAL@v1 calibration for this instance, or None if unzeroed."""
        return self._calibration

    def connect_readonly(self, lock_manager: LockManager | None = None) -> None:
        """Open the bus torque-OFF: bus open + motor register + feedback warmup only.

        Never calls `enable_torque`/`enable_all` and never zeroes — after this returns,
        torque is OFF (02 FR-CON-062, 12 FR-SAF-075). Enforces one connect per session
        (01 FR-SYS-001): a second call raises rather than re-opening (which would
        destroy the established zero).

        The CAN channel lock must be held before any socket opens (01 FR-SYS-005, the
        exclusivity SocketCAN RAW cannot provide itself, 16 §10.1). When a `lock_manager`
        is supplied the bus is opened through `guarded_connect`, which refuses to open
        the socket unless this arm's interface lock is already held. The fixture path
        (a `FakeDamiaoBus`, no real socket) may omit it.

        Args:
            lock_manager: The CAN lock manager holding this arm's interface lock; when
                given, the socket opens only after the lock check passes.

        Raises:
            SessionError: If connect was already called this session.
            LockOrderingError: If a manager is given but this arm's lock is not held.
        """
        if self._connect_count > 0:
            raise SessionError(
                "connect already called this session; a second connect would destroy the "
                "established zero (01 FR-SYS-001)"
            )
        # Count the session's connect only once the socket actually opened: a refused
        # lock check or a failed bus open never opened anything, so it must stay
        # retryable rather than burn the one allowed connect.
        if lock_manager is not None:
            guarded_connect(lock_manager, [self.config.port], self.bus.connect)
        else:
            self.bus.connect()
        self._connect_count += 1
        self._warmup_feedback()
        self._torque_enabled = False
        self._connected_readonly = True

    def connect(self, calibrate: bool = False) -> None:  # noqa: ARG002
        """Bring up the arm torque-OFF; never auto-zero and never enable torque.

        Overrides the stock `connect()` to drop its auto `set_zero_position()` and
        `enable_torque()` (02 FR-CON-061): zeroing is the explicit `set_zero()` flow and
        torque-ON is WP-1-05, neither a side effect of connecting.

        Args:
            calibrate: Accepted for ABC compatibility; never triggers an implicit
                hardware calibration here (that is the whole point of FR-CON-061).
        """
        self.connect_readonly()

    def configure(self) -> None:
        """No-op on the read-only bring-up path.

        The stock `configure()` runs `configure_motors()` inside `torque_disabled`,
        whose context re-enables torque on exit — which would defeat the torque-OFF
        bring-up. MIT parameter configuration belongs to the torque-ON path (WP-1-05),
        so it is deliberately not done here.
        """

    def disable_all(self) -> None:
        """Disable torque on every motor (0xFD), and record torque OFF."""
        self.bus.disable_torque()
        self._torque_enabled = False

    def set_zero(
        self,
        zero_method: ZeroMethod,
        rest_confirmed: bool,
        urdf_zero_offset_deg: list[float] | None = None,
    ) -> ResidualResult:
        """Run the explicit operator zero flow and persist the calibration (FR-CON-063).

        Sequence: refuse if torque is enabled (0xFE is silently skipped on an enabled
        motor, so disable-first is mandatory) → disable all → settle → emit the ONE
        0xFE in the codebase → read the raw angles back → verify the residual against
        the URDF-zero reference → persist atomically. The rest-pose alignment modal
        belongs to THIS step, not `connect()` (FR-CON-063), so `rest_confirmed` gates
        it here.

        Args:
            zero_method: How the mechanical zero reference was established (recorded).
            rest_confirmed: Whether the operator confirmed the arm is aligned to the
                URDF-zero rest pose. Zeroing an unaligned arm is refused.
            urdf_zero_offset_deg: Expected URDF-zero angle per motor; defaults to all
                zeros (the rest pose is the URDF zero).

        Returns:
            (ResidualResult) The per-joint residual measured at zero time.

        Raises:
            SessionError: If called before `connect_readonly()`.
            CalibrationError: If rest is unconfirmed, torque is enabled, or the residual
                exceeds tolerance (re-zero required).
        """
        if not self._connected_readonly:
            raise SessionError("set_zero requires connect_readonly() first")
        if not rest_confirmed:
            raise CalibrationError(
                "set_zero refused: the rest-pose alignment is unconfirmed; align the arm to the "
                "URDF-zero rest pose and confirm before zeroing (02 FR-CON-063)"
            )
        if self._torque_enabled:
            raise CalibrationError(
                "set_zero refused while torque is enabled: 0xFE is silently ignored on an enabled "
                "motor, so disable first (02 FR-CON-063)"
            )

        reference = (
            list(urdf_zero_offset_deg) if urdf_zero_offset_deg is not None else [0.0] * MOTOR_COUNT
        )

        self.disable_all()
        time.sleep(SET_ZERO_SETTLE_SEC)
        # The single 0xFE emission point in the whole codebase (acceptance ③). Every
        # per-motor set-zero goes through this one call.
        #
        # Named motors, never the bare default: `DamiaoMotorsBus.set_zero_position(None)` walks
        # every motor the bus was constructed with, and on a build whose end effector has no
        # gripper that includes an id nothing answers on. An unanswered frame is not an error
        # return — the transmit error counter climbs and the controller falls to ERROR-PASSIVE,
        # which degrades the joints that ARE present. Measured on this bench.
        self.bus.set_zero_position(list(self._fitted_motors()))

        measured = self._read_joint_deg()
        residual = compute_residual(measured, reference)
        if not residual.within_tolerance:
            raise CalibrationError(
                f"zero residual exceeds tolerance for {residual.offenders} "
                f"(residual={residual.residual_deg} deg, tol=±{residual.tolerance_deg}); "
                "re-zero required"
            )

        self._persist_zero(measured, reference, zero_method, residual)
        return residual

    def capture_gripper_endpoint(self, direction: str, rad: float) -> None:
        """Persist a hand-captured gripper endpoint and mark it captured (FR-CON-014 ⑫).

        Args:
            direction: "open" or "close".
            rad: The captured gripper angle (radians).

        Raises:
            SessionError: If no zeroed calibration exists yet (capture follows set_zero).
            ValueError: If `direction` is not "open" or "close".
        """
        calibration = self._calibration
        if calibration is None:
            raise SessionError("capture_gripper_endpoint requires a completed set_zero first")
        if direction == "open":
            calibration.gripper_open_rad = float(rad)
            calibration.gripper_open_captured = True
        elif direction == "close":
            calibration.gripper_close_rad = float(rad)
            calibration.gripper_close_captured = True
        else:
            raise ValueError(
                f"gripper endpoint direction must be 'open' or 'close', got {direction!r}"
            )
        self._calibration = save_calibration_atomic(self._calibration_path(), calibration)

    def send_action(
        self,
        action: RobotAction,
        custom_kp: dict[str, float] | None = None,
        custom_kd: dict[str, float] | None = None,
        feedforward_torque_nm: dict[str, float] | None = None,
    ) -> RobotAction:
        """The safety gateway on the Robot ABC surface — filters every command (11 NFR-INF-008).

        Overrides the stock follower's direct-to-bus `send_action`. It reads the
        present pose, runs the ordered safety filter (unit → zero → limit (2-stage) →
        freshness → workspace/collision → slew → jerk → stopped), records the request
        and the accepted action, and returns the accepted one — a rejected command
        holds at present. This class writes no CAN itself.

        Feed-forward torque (`03` FR-MOT-058) rides beside the action rather than inside
        it: the stock method hardcodes the MIT tuple's `tau` to 0.0, and the fix is to
        route a torque into the same filtered decision the position takes, not to add a
        `{motor}.torque` key. `action` is the recorded training target and CTR-REC@v1
        makes a torque dimension in it the FAIL_BLOCKING defect, so the torque travels as
        its own argument the way it does everywhere else in the actuation spine
        (`TimestampedTarget.feedforward_torque`, `ActuationGateway.submit`). The accepted
        torque leaves on `last_gate_result.feedforward_torque_nm`, one `Nm` per joint, in
        the shape the single writer puts in the fifth `_mit_control_batch` slot; a filter
        rejection zeroes it, so no torque survives a command that held.

        Omitting the torque and passing all zeros are different inputs, not two spellings
        of one: omitting hands the gateway None, the position-only case it distinguishes.

        A torque that is live must also be a torque that stops. The interval since the last
        judged command is the age the FRESHNESS stage reads, so a stream that goes quiet
        for longer than `GATEWAY_FRESHNESS_WINDOW_SEC` gets its next command held at the
        present pose with every joint's feed-forward torque zeroed (`03` FR-MOT-058 ②).
        Zeroing tau is not disabling torque and must not be confused with it: this arm has
        no mechanical brake, so a disable is a fall, while a hold at present with the hold
        gains standing is the arm staying where it is under power.

        Enabling torque is not done here and is not implied by commanding one — engaging
        is WP-1-05's, after PG-SAFE-001.

        The decision is what leaves for the single writer, never the request: the accepted
        vector is offered to the `AcceptedTargetPublisher`, which puts it on the scheduler's
        mailbox once the other arm has offered too. A refusal travels the same way, because
        its accepted channel is the present pose — so the frame the scheduler emits is one
        the filter passed, and an unsafe-rate request reaches the bus as a hold rather than
        as a position clamp of itself.

        A slot the caller leaves out holds at its present angle, so the difference between
        "not commanded" and "commanded by a key nothing reads" is invisible in the returned
        action. A key naming a motor outside the frozen layout is therefore refused rather
        than dropped, the same rule the gain and torque channels already apply.

        Args:
            action: Position action, keys `{motor}.pos` in degrees.
            custom_kp: Optional per-motor stiffness gains, validated against [0,500]; a motor
                left out keeps the hold stiffness.
            custom_kd: Optional per-motor damping gains, validated against [0,5] and against
                the position-command damping floor; a motor left out keeps the hold damping.
            feedforward_torque_nm: Optional per-motor feed-forward torque in newton-metres;
                a motor left out asks for no torque on that joint. None means no torque
                term at all.

        Returns:
            (RobotAction) The accepted position action, keys `{motor}.pos` in degrees.

        Raises:
            ValueError: If a position key names a motor outside the frozen layout.
            TorqueRefusedError: If a commanded torque names an unknown motor or leaves its
                joint's effort band.
            GainRefusedError: If a commanded gain names an unknown motor.
            EndEffectorError: If a non-zero torque lands on the gripper slot of an arm whose
                tool has no motor 0x08.
        """
        _refuse_unknown_position_keys(action)
        present = tuple(Deg(angle) for angle in self._read_joint_deg())
        request = tuple(
            Deg(float(action.get(f"{motor}.pos", present[index].value)))
            for index, motor in enumerate(MOTOR_ORDER)
        )
        torque, kp, kd = self.resolve_command(custom_kp, custom_kd, feedforward_torque_nm)
        result = self._ensure_gateway().submit(
            request,
            present,
            calibrated=self.is_calibrated,
            source_age_sec=self._watchdog.gap_sec(),
            feedforward_torque_nm=torque,
            kp=kp,
            kd=kd,
        )
        self._last_gate_result = result
        if self._publisher is not None:
            self._publisher.offer(self.side, result)
        return {
            f"{motor}.pos": result.accepted[index].value for index, motor in enumerate(MOTOR_ORDER)
        }

    def resolve_command(
        self,
        custom_kp: dict[str, float] | None,
        custom_kd: dict[str, float] | None,
        feedforward_torque_nm: dict[str, float] | None,
    ) -> tuple[tuple[Nm, ...] | None, tuple[float, ...] | None, tuple[float, ...] | None]:
        """Resolve the torque and gain arguments into gateway vectors, raising every refusal.

        Every way this arm can refuse a command outright lives here rather than beside the
        gateway call, so a caller holding two arms can find out whether both would accept
        before either is commanded. Calling it commands nothing and records nothing: no gate
        frame, no history advance, no watchdog mark.

        Args:
            custom_kp: Per-motor stiffness, or None.
            custom_kd: Per-motor damping, or None.
            feedforward_torque_nm: Per-motor feed-forward torque, newton-metres, or None.

        Returns:
            (tuple) The torque vector, the kp vector, and the kd vector, each in MOTOR_ORDER
            or None where the caller supplied nothing.

        Raises:
            TorqueRefusedError: On an unknown motor name or an out-of-band torque.
            GainRefusedError: On a gain naming a motor outside the frozen layout.
            EndEffectorError: On a non-zero gripper-slot torque this arm's tool has no motor for.
        """
        torque = self._resolve_feedforward_torque(feedforward_torque_nm)
        kp = self._resolve_gains(custom_kp, MIT_HOLD_KP, "custom_kp")
        kd = self._resolve_gains(custom_kd, MIT_HOLD_KD, "custom_kd")
        return torque, kp, kd

    def _resolve_gains(
        self, custom: dict[str, float] | None, hold_gain: float, field: str
    ) -> tuple[float, ...] | None:
        """Turn a per-motor gain request into a MOTOR_ORDER vector, refusing unknown motors.

        The vector is filled to full width with the hold gain rather than compacted to the
        keys the caller supplied, because the gateway judges kp and kd as a pair per joint:
        a compacted vector pairs the first named stiffness with the first named damping,
        which are the same joint only by luck, and a rule that holds only by luck is not a
        rule (`03` FR-MOT-021). The fill value is also what the joint is really sent —
        `positions_to_batch` writes `MIT_HOLD_KP`/`MIT_HOLD_KD` into every unnamed slot.

        Args:
            custom: Per-motor gain, or None to command the hold gains on every joint.
            hold_gain: The gain an unnamed motor carries.
            field: The argument name, for the refusal message.

        Returns:
            (tuple[float, ...] | None) The gain in MOTOR_ORDER, or None when the caller
            named no gain at all.

        Raises:
            GainRefusedError: On a motor name outside the frozen layout.
        """
        if custom is None:
            return None
        unknown = sorted(set(custom) - set(MOTOR_ORDER))
        if unknown:
            raise GainRefusedError(
                f"{field} names motors {unknown} that are not in the frozen layout "
                f"{list(MOTOR_ORDER)}; refused rather than dropped, because a mistyped key "
                "otherwise leaves the joint the caller meant to retune on the hold gains"
            )
        return tuple(float(custom.get(motor, hold_gain)) for motor in MOTOR_ORDER)

    def _resolve_feedforward_torque(
        self, feedforward_torque_nm: dict[str, float] | None
    ) -> tuple[Nm, ...] | None:
        """Turn a per-motor torque request into a MOTOR_ORDER vector, refusing out of band.

        Every refusal here fires before the gateway is touched, so a refused command leaves
        no gate frame and no history advance — the arm's recorded state is that nothing was
        commanded, which is what happened.

        Args:
            feedforward_torque_nm: Per-motor feed-forward torque, newton-metres, or None.

        Returns:
            (tuple[Nm, ...] | None) The torque in MOTOR_ORDER, or None when the caller
            asked for no torque term. None and an all-zero vector are deliberately
            distinct: None is the position-only input the gateway takes.

        Raises:
            TorqueRefusedError: On an unknown motor name, or a torque outside the band its
                joint admits.
            EndEffectorError: On a non-zero gripper-slot torque when this arm's tool has no
                motor 0x08.
        """
        if feedforward_torque_nm is None:
            return None
        unknown = sorted(set(feedforward_torque_nm) - set(MOTOR_ORDER))
        if unknown:
            raise TorqueRefusedError(
                f"feed-forward torque names motors {unknown} that are not in the frozen layout "
                f"{list(MOTOR_ORDER)}; refused rather than dropped, because a mistyped key "
                "otherwise sends zero torque to the joint the caller meant to drive"
            )
        resolved: list[Nm] = []
        for index, motor in enumerate(MOTOR_ORDER):
            value = float(feedforward_torque_nm.get(motor, NO_FEEDFORWARD_TORQUE_NM))
            ceiling = FEEDFORWARD_TORQUE_LIMIT_NM[index]
            if ceiling is None:
                # The fitted tool decides whether CAN id 0x08 is a motor at all, so that
                # refusal is the end-effector profile's to make and carries its message.
                self._end_effector.assert_gripper_command_allowed(value)
                if value != NO_FEEDFORWARD_TORQUE_NM:
                    raise TorqueRefusedError(
                        f"{motor} feed-forward torque {value} Nm is refused: the URDF declares "
                        "no effort figure for this slot, and grip force is a per-unit current "
                        "limit rather than a torque in newton-metres (03 FR-MOT-047)"
                    )
            elif not -ceiling <= value <= ceiling:
                raise TorqueRefusedError(
                    f"{motor} feed-forward torque {value} Nm is outside the effort band "
                    f"[{-ceiling:.4g}, {ceiling:.4g}] Nm (URDF effort limit); refused, not clamped"
                )
            resolved.append(Nm(value))
        return tuple(resolved)

    def get_observation(self) -> RobotObservation:
        """Return the stock observation plus the CAN packet-drop counter (01 FR-SYS-018).

        LeRobot logs a drop and reuses the last state, so the drop count never becomes
        a feature. This surfaces the counter's tally under the frozen
        `can_packet_drop_count` name, so a consumer sees drops rather than losing them
        to a warning (acceptance ⑮).
        """
        observation = super().get_observation()
        observation[DROP_COUNTER_META] = self._drop_counter.count
        return observation

    def enable_drop_counting(self) -> None:
        """Start surfacing the CAN packet-drop count (attach the logger counter)."""
        self._drop_counter.attach()

    def disable_drop_counting(self) -> None:
        """Stop surfacing the CAN packet-drop count (detach the logger counter)."""
        self._drop_counter.detach()

    @property
    def gateway(self) -> ActuationGateway:
        """The single enforcement gateway `send_action` routes through."""
        return self._ensure_gateway()

    @property
    def drop_counter(self) -> DropCounter:
        """The CAN packet-drop counter surfaced in the observation."""
        return self._drop_counter

    @property
    def last_gate_result(self) -> GateResult | None:
        """The gateway decision from the most recent `send_action`, or None."""
        return self._last_gate_result

    def _ensure_gateway(self) -> ActuationGateway:
        """Return the enforcement gateway, building it on first use from this arm's side."""
        if self._gateway is None:
            self._gateway = self._build_gateway()
        return self._gateway

    def _build_gateway(self) -> ActuationGateway:
        """Build the arm's enforcement gateway: the ordered filter and fail-closed guard."""
        guard = CollisionGuard(on_latch=self._on_collision_latch, clock=self._clock)
        return ActuationGateway(
            safety_filter=SafetyFilter(build_safety_limits(self.side)),
            guard=guard,
            dt_sec=CONTROL_PERIOD_SEC,
            freshness_window_sec=GATEWAY_FRESHNESS_WINDOW_SEC,
        )

    def _on_collision_latch(self, reason: LatchReason) -> None:
        """Record a collision-guard latch cause; the latch holds until an operator ack.

        The guard never writes the bus (`12` FR-SAF-074 ③): it records the cause here,
        and the latch it set makes every subsequent gateway command hold.
        """
        self._last_latch_reason = reason

    def disconnect(self) -> None:
        """Go offline torque-OFF, disabling torque on the way out."""
        if self.bus.is_connected:
            self.bus.disconnect(True)
        for cam in self.cameras.values():
            cam.disconnect()
        self._torque_enabled = False
        self._connected_readonly = False

    def _persist_zero(
        self,
        measured: list[float],
        reference: list[float],
        zero_method: ZeroMethod,
        residual: ResidualResult,
    ) -> None:
        """Build and atomically persist the calibration produced by a set-zero.

        Gripper captured flags are reset: 0xFE re-zeros the gripper motor too, so the
        previously captured open/close endpoints are now referenced to a shifted zero
        and must be re-captured. Signs, scale, and the endpoint values carry over from
        any prior calibration as seeds.
        """
        prior = self._calibration
        calibration = OpenArmCalibration(
            robot_type=self.name,
            robot_id=self.id,
            side=self.side,
            motor_zero_raw=measured,
            urdf_zero_offset=reference,
            gripper_open_rad=prior.gripper_open_rad if prior else GRIPPER_OPEN_DEFAULT_RAD,
            gripper_close_rad=prior.gripper_close_rad if prior else GRIPPER_CLOSE_DEFAULT_RAD,
            joint_signs=list(prior.joint_signs) if prior else [DEFAULT_JOINT_SIGN] * MOTOR_COUNT,
            joint_scale=list(prior.joint_scale) if prior else [DEFAULT_JOINT_SCALE] * MOTOR_COUNT,
            gripper_open_captured=False,
            gripper_close_captured=False,
            zero_method=zero_method,
            zero_residual_deg=list(residual.residual_deg),
            created_at=prior.created_at if prior else None,
            last_zero_at=_utc_now_iso(),
        )
        self._calibration = save_calibration_atomic(self._calibration_path(), calibration)

    def _calibration_path(self) -> Path:
        """Return the CTR-CAL@v1 calibration file path for this instance."""
        return calibration_path_for(self.calibration_dir, self.id)

    def _load_oa_calibration(self) -> OpenArmCalibration | None:
        """Load this instance's calibration from disk, or None if absent."""
        path = self._calibration_path()
        if path.is_file():
            return load_calibration(path)
        return None

    def _warmup_feedback(self) -> None:
        """Read the motor states once to warm the feedback cache (torque untouched)."""
        self.bus.sync_read_all_states(list(self._fitted_motors()))

    def _fitted_motors(self) -> tuple[str, ...]:
        """The motor names this arm actually carries, in MOTOR_ORDER order.

        `MOTOR_ORDER` is the frozen eight-slot contract, not an inventory: the gripper slot is
        always in the layout and the gripper motor is not always on the bus. Every bus call keys
        on the fitted end effector so no frame is addressed to an absent motor.
        """
        profile = self._end_effector
        if profile.has_actuated_gripper:
            return tuple(MOTOR_ORDER)
        return tuple(name for name in MOTOR_ORDER if name != GRIPPER_MOTOR_NAME)

    def _read_joint_deg(self) -> list[float]:
        """Read the current raw joint angles (degrees) in MOTOR_ORDER.

        The poll names the fitted motors and the answer is widened back to the frozen layout, so
        a slot with no motor behind it reports the same zero it always did without a frame being
        addressed to it. `sync_read_all_states()` with no argument walks every motor the bus was
        constructed with, and on this bench that includes an id that answered 0 of 20 polls —
        sixteen unanswered frames took both channels to ERROR-PASSIVE. This read runs once per
        `send_action`, so the bare form was one unanswered frame per command.
        """
        states = self.bus.sync_read_all_states(list(self._fitted_motors()))
        return [float(states.get(motor, {}).get("position", 0.0)) for motor in MOTOR_ORDER]


def _refuse_unknown_position_keys(action: RobotAction) -> None:
    """Refuse a position key whose motor is outside the frozen layout.

    The request vector is built by looking `{motor}.pos` up for each slot of `MOTOR_ORDER`, so a
    key naming anything else contributes nothing and its joint holds at its present angle while
    every other joint obeys — an arm that partly did what it was told, with a returned action that
    looks like a complete answer. The gain and torque channels refuse an unknown motor name for
    exactly this reason; position is the channel a caller types most often.

    What is checked is the motor name, not the channel suffix: `use_velocity_and_torque` puts
    `{motor}.vel` and `{motor}.torque` in the same feature space, and those are channels this
    override does not read rather than motors the arm does not have.

    Args:
        action: The position action, keys `{motor}.pos` in degrees.

    Raises:
        ValueError: When a key names a motor no arm carries.
    """
    unknown = sorted(key for key in action if key.partition(".")[0] not in MOTOR_ORDER)
    if unknown:
        raise ValueError(
            f"action keys {unknown} name motors that are not in the frozen layout "
            f"{list(MOTOR_ORDER)}; refused rather than dropped, because a dropped key leaves the "
            "joint the caller meant to move holding at present while the rest of the arm obeys"
        )


def _refuse_unsided(mapping: dict[str, float] | None, field: str, error: type[ValueError]) -> None:
    """Refuse a bimanual per-motor argument whose key names neither arm.

    The split is by prefix, so a key with neither prefix reaches no arm and the joint the
    caller named silently keeps its default. That is the same failure the per-arm path
    refuses an unknown motor name for, one level up.

    Args:
        mapping: The per-motor argument, or None.
        field: The argument name, for the refusal message.
        error: The refusal this argument's contract raises.

    Raises:
        ValueError: Of the given type, when a key carries no side prefix.
    """
    if mapping is None:
        return
    unsided = sorted(
        key for key in mapping if not any(key.startswith(f"{side}_") for side in SIDE_PREFIXES)
    )
    if unsided:
        raise error(
            f"{field} keys {unsided} name neither arm; a bimanual key is "
            f"{{side}}_{{motor}} with side in {list(SIDE_PREFIXES)}, and an unsided key "
            "reaches no arm at all"
        )


def _for_side(mapping: dict[str, float] | None, prefix: str) -> dict[str, float] | None:
    """Narrow a bimanual per-motor argument to one arm, stripping the side prefix.

    An arm the caller named nothing for gets None, not an empty mapping. The two are
    different inputs one level down: `_resolve_feedforward_torque({})` fills an eight-slot
    all-zero Nm vector, which is a commanded zero torque on every joint, while None is the
    position-only case the gateway takes. Naming one arm is not a statement about the other,
    so the unnamed arm must be indistinguishable from a caller who passed no torque at all.

    Args:
        mapping: The per-motor argument keyed `{side}_{motor}`, or None.
        prefix: The side to narrow to.

    Returns:
        (dict[str, float] | None) The entries for this side keyed by bare motor name, or
        None when the caller named nothing for this side.
    """
    if mapping is None:
        return None
    narrowed = {
        key[len(prefix) + 1 :]: value
        for key, value in mapping.items()
        if key.startswith(f"{prefix}_")
    }
    return narrowed or None


class BiOaOpenArmFollower(OpenArmRobot):
    """The bimanual hardware OpenArm follower: two arms with partial-connect handling.

    Ownership: owns its two `OaOpenArmFollower` arms. Composing rather than opening two
    buses itself keeps the per-arm bring-up, zero, and calibration logic in one place.
    Inherits the frozen 48/16 feature contract from `OpenArmRobot`.
    """

    name = BI_OA_FOLLOWER_TYPE
    config_class = BiOaOpenArmFollowerConfig

    def __init__(
        self,
        config: BiOaOpenArmFollowerConfig,
        left: OaOpenArmFollower | None = None,
        right: OaOpenArmFollower | None = None,
        publisher: AcceptedTargetPublisher | None = None,
    ) -> None:
        """Construct the bimanual follower and its two arms without opening any bus.

        Args:
            config: The bimanual plugin config.
            left: An optional pre-built left arm (fixtures inject a fixture-bus arm).
            right: An optional pre-built right arm.
            publisher: The shared publisher onto the scheduler's mailbox, given to the arms
                this constructor builds. An injected arm arrives with its own, the way it
                arrives with its own bus and clock.
        """
        super().__init__(config)
        self.left_arm = left if left is not None else self._build_arm(config, Side.LEFT, publisher)
        self.right_arm = (
            right if right is not None else self._build_arm(config, Side.RIGHT, publisher)
        )
        self._connected = False

    def _build_arm(
        self,
        config: BiOaOpenArmFollowerConfig,
        side: Side,
        publisher: AcceptedTargetPublisher | None,
    ) -> OaOpenArmFollower:
        """Build one arm's follower from the bimanual config, namespaced by side."""
        arm_config = OaOpenArmFollowerConfig(
            id=f"{config.id}_{side.value}",
            calibration_dir=config.calibration_dir,
            side=side,
            use_velocity_and_torque=config.use_velocity_and_torque,
        )
        return OaOpenArmFollower(arm_config, publisher=publisher)

    @property
    def is_connected(self) -> bool:
        """Whether both arms are connected."""
        return self.left_arm.is_connected and self.right_arm.is_connected

    @property
    def is_calibrated(self) -> bool:
        """Whether both arms have a completed set-zero."""
        return self.left_arm.is_calibrated and self.right_arm.is_calibrated

    @property
    def is_torque_enabled(self) -> bool:
        """Whether either arm has torque enabled (never, during WP-1-02 bring-up)."""
        return self.left_arm.is_torque_enabled or self.right_arm.is_torque_enabled

    def connect_readonly(self, lock_manager: LockManager | None = None) -> None:
        """Bring both arms up torque-OFF, left then right; never orphan a partial connect.

        Left connects first, then right. If right fails, the left connection is torn
        down before raising: a half-connected pair must not be left running and the
        surviving arm must not be left orphaned (01 §4.2 T1). The lock manager, when
        given, must already hold both arms' interface locks (01 FR-SYS-005).

        Args:
            lock_manager: The CAN lock manager holding both arms' interface locks.

        Raises:
            PartialConnectionError: If one arm connects and the other fails.
        """
        self.left_arm.connect_readonly(lock_manager)
        try:
            self.right_arm.connect_readonly(lock_manager)
        except Exception as exc:
            self.left_arm.disconnect()
            raise PartialConnectionError(
                "right arm failed to connect; tore down the left arm rather than run a "
                "half-connected bimanual pair (01 §4.2 T1)"
            ) from exc
        self._connected = True

    def connect(self, calibrate: bool = False) -> None:  # noqa: ARG002
        """Bring up both arms torque-OFF; never auto-zero and never enable torque."""
        self.connect_readonly()

    def calibrate(self) -> None:
        """No-op: zeroing is the explicit per-arm `set_zero()` operator flow."""

    def configure(self) -> None:
        """No-op on the read-only bring-up path (see `OaOpenArmFollower.configure`)."""

    def disconnect(self) -> None:
        """Disconnect both arms."""
        self.left_arm.disconnect()
        self.right_arm.disconnect()
        self._connected = False

    def get_observation(self) -> RobotObservation:
        """Merge both arms' frames under the frozen `left_`/`right_` channel names.

        The CAN drop counter is observation *meta* rather than a per-arm channel: the ABC
        declares it unprefixed for the bimanual robot too, so prefixing it emits two keys
        the declared feature set does not contain and omits the one it does. LeRobot builds
        a dataset's features from that declaration, so a prefixed counter is dropped from
        every recorded episode — and the tally is the only signal that motor feedback
        frames were lost, which is what makes a lossy-bus episode indistinguishable from a
        clean one. The two arms share one bus lock and one counter semantic, so the robot's
        count is their sum.
        """
        observation: dict[str, float | int] = {}
        dropped = 0
        for prefix, arm in self._sided_arms:
            for channel, value in arm.get_observation().items():
                if channel == DROP_COUNTER_META:
                    dropped += int(value)
                    continue
                observation[f"{prefix}_{channel}"] = value
        observation[DROP_COUNTER_META] = dropped
        return observation

    def send_action(
        self,
        action: RobotAction,
        custom_kp: dict[str, float] | None = None,
        custom_kd: dict[str, float] | None = None,
        feedforward_torque_nm: dict[str, float] | None = None,
    ) -> RobotAction:
        """Split a bimanual action by `left_`/`right_` prefix and delegate per arm.

        WP-1-03 adds the safety gateway to the per-arm `send_action`; the bimanual
        routes through those single enforcement points rather than around them.

        Gains and feed-forward torque split on the same prefix as the position keys, so the
        registered bimanual plugin type reaches the torque path (`03` FR-MOT-058) without a
        caller having to hold `.left_arm` / `.right_arm` — reaching past the pair is how a
        command gets sent to one arm with the other still commanded by whoever held it last.

        Both arms are judged before either is commanded, so the pair is refused whole. A
        refusal raised halfway through the split leaves the first arm already commanded and
        the second untouched, with the caller holding an exception and no way to tell which
        half landed — the same one-arm-commanded state reaching past the pair produces, and
        the reason this class exists. So the split runs in two passes: the first narrows each
        side's arguments and asks every refusal a per-arm command can raise — the position
        keys here, the gains and the torque through `resolve_command` — and commands nothing;
        the second commands both arms from what the first pass already accepted.

        The two accepted decisions become one mailbox target. Each arm offers its own to the
        shared publisher and the slot swaps only on the second offer, so the single writer
        never reads a bimanual frame whose halves came from different commands.

        Args:
            action: Bimanual position action, keys `{side}_{motor}.pos` in degrees.
            custom_kp: Optional per-motor stiffness, keys `{side}_{motor}`.
            custom_kd: Optional per-motor damping, keys `{side}_{motor}`.
            feedforward_torque_nm: Optional per-motor feed-forward torque in newton-metres,
                keys `{side}_{motor}`.

        Returns:
            (RobotAction) The accepted bimanual position action.

        Raises:
            ValueError: If a position key names no arm, or names a motor no arm carries.
            TorqueRefusedError: If a torque key names no arm, or an arm refuses it.
            GainRefusedError: If a gain key names no arm, or an arm refuses it.
        """
        _refuse_unsided(action, "action", ValueError)
        _refuse_unsided(feedforward_torque_nm, "feedforward_torque_nm", TorqueRefusedError)
        _refuse_unsided(custom_kp, "custom_kp", GainRefusedError)
        _refuse_unsided(custom_kd, "custom_kd", GainRefusedError)
        judged: list[tuple[str, OaOpenArmFollower, RobotAction]] = []
        for prefix, arm in self._sided_arms:
            arm_action = {
                key[len(prefix) + 1 :]: value
                for key, value in action.items()
                if key.startswith(f"{prefix}_")
            }
            _refuse_unknown_position_keys(arm_action)
            arm.resolve_command(
                _for_side(custom_kp, prefix),
                _for_side(custom_kd, prefix),
                _for_side(feedforward_torque_nm, prefix),
            )
            judged.append((prefix, arm, arm_action))
        applied: dict[str, float] = {}
        for prefix, arm, arm_action in judged:
            accepted = arm.send_action(
                arm_action,
                custom_kp=_for_side(custom_kp, prefix),
                custom_kd=_for_side(custom_kd, prefix),
                feedforward_torque_nm=_for_side(feedforward_torque_nm, prefix),
            )
            for key, value in accepted.items():
                applied[f"{prefix}_{key}"] = value
        return applied

    @property
    def _sided_arms(self) -> tuple[tuple[str, OaOpenArmFollower], ...]:
        """The two arms paired with the prefix their channels carry, in `SIDE_PREFIXES` order.

        The prefixes the split refuses an unsided key against and the prefixes it then splits
        on are one tuple, so a third side could not be accepted by one and dropped by the other.
        """
        return tuple(zip(SIDE_PREFIXES, (self.left_arm, self.right_arm), strict=True))
