"""Builders and scripted-rig helpers for the WP-2B-06 injection suite.

The helpers keep every test in one vocabulary. `RecordingTorquePath` is a torque sink
that records what the harness commanded (the recording double the deferred real path
stands in for). `build_context` wires a real `RealSendBarrier`, a real one-way
`SafetyLatch`, the reused `backend.commloss` watchdog, the committed v2 gravity backend,
and an `ExcitationInjector`, so a gate or a latch a test observes is the production one,
not a stand-in. The observer factories script one tick's rig report and inject exactly
one fault at a chosen index, which is how the abort-on-fault paths are proven without
hardware.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.actuation import ManualClock, SafetyLatch
from backend.commloss import CommLossWatchdog
from backend.dynamics import ARM_JOINT_COUNT
from backend.excitation import (
    AbortMonitor,
    ExcitationInjector,
    ExcitingTrajectory,
    JointBounds,
    JointExcitation,
    Observer,
    TickObservation,
    TorqueCommand,
    TrajectorySample,
    design_band,
)
from backend.gravity import Arm, BackendId, GravityBackend, select_backend
from backend.interlock import RealSendBarrier
from contracts.errors.constants import DAMIAO_ENABLE_NIBBLE
from sim.dryrun.violation import DryRunVerdict

# A Damiao status byte: the ERR nibble packed into the high nibble of `data[0]`.
HEALTHY_BYTE = DAMIAO_ENABLE_NIBBLE << 4
OVERVOLTAGE_FAULT_BYTE = 0x8 << 4  # nibble 8 stands in for any decoded motor fault

# Right-arm v2 joint bounds [rad], joint1..joint7, from the committed v2 MJCF (the same
# limits the WP-2B-02 suite reads), with a generous per-joint speed ceiling.
_POSITION_LIMITS = (
    (-1.3963, 3.4907),
    (-0.17453, 3.3161),
    (-1.5708, 1.5708),
    (0.0, 2.4435),
    (-1.5708, 1.5708),
    (-0.7854, 0.7854),
    (-1.5708, 1.5708),
)
_VELOCITY_MAX_RAD_S = 8.0
ARM_BOUNDS: tuple[JointBounds, ...] = tuple(
    JointBounds(low, high, _VELOCITY_MAX_RAD_S) for low, high in _POSITION_LIMITS
)

# A rest pose inside every bound and inside the v2 joint2 range; the trajectory
# oscillates a small amplitude about it.
REST_POSE: tuple[float, ...] = (0.0, 1.4, 0.0, 1.0, 0.0, 0.0, 0.0)
_EXCITATION_AMPLITUDE_RAD = 0.05


class RecordingTorquePath:
    """A `TorqueCommandPath` that records each command instead of driving hardware."""

    def __init__(self) -> None:
        """Start with an empty command log."""
        self.commands: list[TorqueCommand] = []

    def send(self, command: TorqueCommand) -> None:
        """Record one command.

        Args:
            command: The MIT command the harness would have emitted.
        """
        self.commands.append(command)

    @property
    def commanded_indices(self) -> list[int]:
        """The trajectory indices commanded, in order."""
        return [command.index for command in self.commands]


def build_trajectory(
    logging_frequency_hz: float = 1000.0, duration_s: float = 0.02
) -> ExcitingTrajectory:
    """Build a small in-bounds trajectory centred on the rest pose.

    Args:
        logging_frequency_hz: The rate the band is derived from.
        duration_s: Session length; the default gives 20 samples at 1 kHz.

    Returns:
        (ExcitingTrajectory) A limit-respecting trajectory over all seven joints.
    """
    band = design_band(logging_frequency_hz)
    joints = [
        JointExcitation(center_rad=REST_POSE[index], amplitude_rad=_EXCITATION_AMPLITUDE_RAD)
        for index in range(ARM_JOINT_COUNT)
    ]
    return ExcitingTrajectory(
        band=band, joints=joints, bounds=list(ARM_BOUNDS), duration_s=duration_s
    )


def gravity_backend() -> GravityBackend:
    """Build the committed v2 gravity backend for the right arm."""
    return select_backend(BackendId.MUJOCO_V2, Arm.RIGHT)


@dataclass
class InjectionContext:
    """The wired injector plus the handles a test drives and inspects.

    Attributes:
        injector: The harness under test.
        latch: The shared one-way safety latch every abort engages.
        clock: The manual clock the watchdog and monitor read.
        torque_path: The recording torque sink, or None when the ④ path is unwired.
        trajectory: The trajectory being injected.
        watchdog: The reused comm-loss watchdog.
    """

    injector: ExcitationInjector
    latch: SafetyLatch
    clock: ManualClock
    torque_path: RecordingTorquePath | None
    trajectory: ExcitingTrajectory
    watchdog: CommLossWatchdog


def build_context(
    observer: Observer,
    armed: bool = True,
    torque_path_present: bool = True,
    comm_timeout_sec: float = 0.010,
    trajectory: ExcitingTrajectory | None = None,
    clock: ManualClock | None = None,
) -> InjectionContext:
    """Wire an injector over production collaborators and a scripted observer.

    Args:
        observer: The scripted rig report source.
        armed: Whether to arm the dry-run barrier with a passing verdict.
        torque_path_present: Whether to wire a torque path (False exercises the ④ gate).
        comm_timeout_sec: The watchdog silence ceiling.
        trajectory: An optional pre-built trajectory; a default is built when None.
        clock: An optional shared clock; a comm-loss observer passes the one it advances.

    Returns:
        (InjectionContext) The injector and its handles.
    """
    latch = SafetyLatch()
    clock = clock if clock is not None else ManualClock()
    watchdog = CommLossWatchdog(latch=latch, clock=clock, comm_timeout_sec=comm_timeout_sec)
    monitor = AbortMonitor(watchdog=watchdog, latch=latch, clock=clock, bounds=ARM_BOUNDS)
    resolved_trajectory = trajectory if trajectory is not None else build_trajectory()
    torque_path = RecordingTorquePath() if torque_path_present else None

    barrier = RealSendBarrier()
    if armed:
        verdict = DryRunVerdict(violations=(), asset_digest="wp2b06-fixture", backend="mujoco")
        barrier.gate(verdict)

    def permits_real_send() -> bool:
        return barrier.permits_real_send

    def latch_is_active() -> bool:
        return latch.is_active

    injector = ExcitationInjector(
        barrier_permits_real_send=permits_real_send,
        torque_path=torque_path,
        gravity=gravity_backend(),
        monitor=monitor,
        trajectory=resolved_trajectory,
        observer=observer,
        bounds=ARM_BOUNDS,
        latch_is_active=latch_is_active,
    )
    return InjectionContext(
        injector=injector,
        latch=latch,
        clock=clock,
        torque_path=torque_path,
        trajectory=resolved_trajectory,
        watchdog=watchdog,
    )


def healthy_tick(
    positions_rad: Sequence[float], velocities_rad_s: Sequence[float]
) -> TickObservation:
    """Return a clean tick observation matching a sample's own state."""
    return TickObservation(
        status_bytes=[HEALTHY_BYTE] * ARM_JOINT_COUNT,
        motor_temps_c=[25.0] * ARM_JOINT_COUNT,
        positions_rad=list(positions_rad),
        velocities_rad_s=list(velocities_rad_s),
        human_abort=False,
    )


def healthy_observer() -> Observer:
    """Return an observer that reports every tick clean, echoing the sample's own state."""

    def _observe(index: int, sample: TrajectorySample) -> TickObservation:
        return healthy_tick(sample.positions_rad, sample.velocities_rad_s)

    return _observe
