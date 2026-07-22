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
    ActuationGateway,
    CollisionGuard,
    DropCounter,
    GateResult,
    SafetyFilter,
    SafetyLimits,
    WallClock,
)
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
# so a placeholder here never affects the offline flow.
PORT_BY_SIDE = {"left": "can0", "right": "can1"}
_DEFAULT_PORT = "can0"

# Seconds to let the arm settle after disabling torque before emitting 0xFE, so the
# zero is captured on a mechanically-still arm rather than mid-sag (02 FR-CON-063).
SET_ZERO_SETTLE_SEC = 0.2

# Gripper endpoint seeds (radians). v2 pinch is a revolute joint over −45°..0° with no
# load cell, so the real endpoints are captured by hand (16 D-5); these are only the
# pre-capture defaults, and their `captured` flags stay False until a hand capture.
GRIPPER_OPEN_DEFAULT_RAD = 0.0
GRIPPER_CLOSE_DEFAULT_RAD = math.radians(-45.0)

# Physical Peak Torque per motor, newton-metres (03 FR-MOT-037): J1/J2 (DM8009) 40,
# J3/J4 (DM4340) 27; J5-J7 and the gripper (DM4310) 10 (10 §2.3). This is the axis a
# torque clamp uses — never the packet-scale T_MAX (DM8009 54 / DM4340 28 / DM4310 10),
# which is wider on the shoulders and would admit a shoulder over-torque if used as the
# clamp bound. The operational torque bound defaults to the peak (a valid subset).
PEAK_TORQUE_NM = (40.0, 40.0, 27.0, 27.0, 10.0, 10.0, 10.0, 10.0)

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

# Age past which the source target is stale (matches the actuation spine's window).
GATEWAY_FRESHNESS_WINDOW_SEC = 0.05


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
    """

    name = OA_FOLLOWER_TYPE
    config_class = OaOpenArmFollowerConfig

    def __init__(
        self,
        config: OaOpenArmFollowerConfig,
        bus: DamiaoMotorsBus | None = None,
        gateway: ActuationGateway | None = None,
        drop_counter: DropCounter | None = None,
    ) -> None:
        """Construct the follower without opening any bus.

        Args:
            config: The plugin config; `side` is required (validated by the config).
            bus: An optional bus to use instead of building the real `DamiaoMotorsBus`
                — the seam fixtures use to exercise the flow with no CAN present.
            gateway: An optional pre-built enforcement gateway (a fixture injects one
                over a fake CAN writer); built lazily from this arm's side otherwise.
            drop_counter: An optional CAN packet-drop counter; a fresh one otherwise.
        """
        self._plugin_config = config
        super().__init__(self._build_hardware_config(config))
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

    def _build_hardware_config(self, config: OaOpenArmFollowerConfig) -> OpenArmFollowerConfig:
        """Build the full LeRobot hardware config from the minimal plugin config.

        The plugin config carries only `side` and the velocity/torque switch (the
        frozen CTR-PLUG@v1 surface); the CAN and motor hardware fields come from
        LeRobot's follower defaults, and the port is derived from the side.

        Args:
            config: The plugin config.

        Returns:
            (OpenArmFollowerConfig) The full hardware config.

        Raises:
            SessionError: If the config has no side (the config layer should have
                already refused this).
        """
        if config.side is None:
            raise SessionError("OaOpenArmFollower requires a side; the config must set left|right")
        side_str = config.side.value
        return OpenArmFollowerConfig(
            id=config.id,
            calibration_dir=config.calibration_dir,
            port=PORT_BY_SIDE.get(side_str, _DEFAULT_PORT),
            side=side_str,
            use_velocity_and_torque=config.use_velocity_and_torque,
        )

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
        self.bus.set_zero_position()

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
    ) -> RobotAction:
        """The safety gateway on the Robot ABC surface — filters every command (11 NFR-INF-008).

        Overrides the stock follower's direct-to-bus `send_action`. It reads the
        present pose, runs the ordered safety filter (unit → zero → limit (2-stage) →
        freshness → workspace/collision → slew → jerk → stopped), records the request
        and the accepted action, and returns the accepted one — a rejected command
        holds at present. This class writes no CAN itself.

        Integration boundary (honest scope): the accepted output is not yet published
        onto the `ActuationScheduler` mailbox. The gateway, the filter, and the
        scheduler/single-writer exist as verified components, but the runtime assembly
        that joins them into one running robot is not built here — so the full 8-check
        filter is enforced on this ABC path, while the scheduler still emits the
        position-clamped mailbox target. Wiring the accepted output onto the mailbox
        (so the single writer enforces the full filter, un-bypassably) is done at
        WP-1-05, when torque-ON activates and the gap becomes load-bearing. Until then
        no motor moves and the gap is inert; `tests/wp103/test_gateway_write_path_assembly.py`
        marks it as the pending integration.

        Args:
            action: Position action, keys `{motor}.pos` in degrees.
            custom_kp: Optional per-motor stiffness gains, validated against [0,500].
            custom_kd: Optional per-motor damping gains, validated against [0,5].

        Returns:
            (RobotAction) The accepted position action, keys `{motor}.pos` in degrees.
        """
        present = tuple(Deg(angle) for angle in self._read_joint_deg())
        request = tuple(
            Deg(float(action.get(f"{motor}.pos", present[index].value)))
            for index, motor in enumerate(MOTOR_ORDER)
        )
        kp = tuple(float(value) for value in custom_kp.values()) if custom_kp else None
        kd = tuple(float(value) for value in custom_kd.values()) if custom_kd else None
        result = self._ensure_gateway().submit(
            request,
            present,
            calibrated=self.is_calibrated,
            kp=kp,
            kd=kd,
        )
        self._last_gate_result = result
        return {
            f"{motor}.pos": result.accepted[index].value for index, motor in enumerate(MOTOR_ORDER)
        }

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
        guard = CollisionGuard(on_latch=self._on_collision_latch, clock=WallClock())
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
        self.bus.sync_read_all_states()

    def _read_joint_deg(self) -> list[float]:
        """Read the current raw joint angles (degrees) in MOTOR_ORDER."""
        states = self.bus.sync_read_all_states()
        return [float(states.get(motor, {}).get("position", 0.0)) for motor in MOTOR_ORDER]


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
    ) -> None:
        """Construct the bimanual follower and its two arms without opening any bus.

        Args:
            config: The bimanual plugin config.
            left: An optional pre-built left arm (fixtures inject a fixture-bus arm).
            right: An optional pre-built right arm.
        """
        super().__init__(config)
        self.left_arm = left if left is not None else self._build_arm(config, Side.LEFT)
        self.right_arm = right if right is not None else self._build_arm(config, Side.RIGHT)
        self._connected = False

    def _build_arm(self, config: BiOaOpenArmFollowerConfig, side: Side) -> OaOpenArmFollower:
        """Build one arm's follower from the bimanual config, namespaced by side."""
        arm_config = OaOpenArmFollowerConfig(
            id=f"{config.id}_{side.value}",
            calibration_dir=config.calibration_dir,
            side=side,
            use_velocity_and_torque=config.use_velocity_and_torque,
        )
        return OaOpenArmFollower(arm_config)

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
        """Merge both arms' frames under the frozen `left_`/`right_` channel names."""
        observation: dict[str, float | int] = {}
        for prefix, arm in (("left", self.left_arm), ("right", self.right_arm)):
            for channel, value in arm.get_observation().items():
                observation[f"{prefix}_{channel}"] = value
        return observation

    def send_action(self, action: RobotAction) -> RobotAction:
        """Split a bimanual action by `left_`/`right_` prefix and delegate per arm.

        WP-1-03 adds the safety gateway to the per-arm `send_action`; the bimanual
        routes through those single enforcement points rather than around them.
        """
        applied: dict[str, float] = {}
        for prefix, arm in (("left", self.left_arm), ("right", self.right_arm)):
            arm_action = {
                key[len(prefix) + 1 :]: value
                for key, value in action.items()
                if key.startswith(f"{prefix}_")
            }
            for key, value in arm.send_action(arm_action).items():
                applied[f"{prefix}_{key}"] = value
        return applied
