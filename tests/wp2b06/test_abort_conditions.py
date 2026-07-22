"""Each abort condition immediately stops injection (`02b` §2.3 ②), proven on mocks.

The four conditions — ERR nibble (a decoded motor fault), comm loss (silence), over-
temperature, joint limit — plus the human abort each fire once at a chosen index and must
stop the run at that index, engage the shared safety latch, and leave every command up to
but not including the abort tick. The ERR-nibble and comm-loss causes are the reused
`backend.commloss` watchdog, so a real decoded fault and a real timed silence drive them.
"""

from __future__ import annotations

from backend.actuation import ManualClock
from backend.dynamics import ARM_JOINT_COUNT
from backend.excitation import (
    AbortCause,
    InjectionStatus,
    Observer,
    SafeInitialState,
    TickObservation,
    TrajectorySample,
)
from tests.wp2b06.support import (
    HEALTHY_BYTE,
    OVERVOLTAGE_FAULT_BYTE,
    REST_POSE,
    build_context,
    healthy_tick,
)

_ABORT_INDEX = 4


def _confirmed() -> SafeInitialState:
    return SafeInitialState(True, True, True, REST_POSE)


def _motor_fault_observer(fault_index: int) -> Observer:
    def _observe(index: int, sample: TrajectorySample) -> TickObservation:
        if index == fault_index:
            bytes_with_fault = [OVERVOLTAGE_FAULT_BYTE] + [HEALTHY_BYTE] * (ARM_JOINT_COUNT - 1)
            return TickObservation(
                status_bytes=bytes_with_fault,
                motor_temps_c=[25.0] * ARM_JOINT_COUNT,
                positions_rad=list(sample.positions_rad),
                velocities_rad_s=list(sample.velocities_rad_s),
                human_abort=False,
            )
        return healthy_tick(sample.positions_rad, sample.velocities_rad_s)

    return _observe


def _comm_loss_observer(loss_index: int, clock: ManualClock) -> Observer:
    def _observe(index: int, sample: TrajectorySample) -> TickObservation:
        if index == loss_index:
            # Model time passing with no frame arriving: advance past the silence ceiling.
            clock.advance(0.05)
            return TickObservation(
                status_bytes=(),
                motor_temps_c=[25.0] * ARM_JOINT_COUNT,
                positions_rad=list(sample.positions_rad),
                velocities_rad_s=list(sample.velocities_rad_s),
                human_abort=False,
            )
        return healthy_tick(sample.positions_rad, sample.velocities_rad_s)

    return _observe


def _over_temp_observer(hot_index: int) -> Observer:
    def _observe(index: int, sample: TrajectorySample) -> TickObservation:
        temps = [25.0] * ARM_JOINT_COUNT
        if index == hot_index:
            temps[2] = 95.0
        return TickObservation(
            status_bytes=[HEALTHY_BYTE] * ARM_JOINT_COUNT,
            motor_temps_c=temps,
            positions_rad=list(sample.positions_rad),
            velocities_rad_s=list(sample.velocities_rad_s),
            human_abort=False,
        )

    return _observe


def _joint_limit_observer(limit_index: int) -> Observer:
    def _observe(index: int, sample: TrajectorySample) -> TickObservation:
        positions = list(sample.positions_rad)
        if index == limit_index:
            positions[0] = 5.0  # past joint1's upper bound
        return TickObservation(
            status_bytes=[HEALTHY_BYTE] * ARM_JOINT_COUNT,
            motor_temps_c=[25.0] * ARM_JOINT_COUNT,
            positions_rad=positions,
            velocities_rad_s=list(sample.velocities_rad_s),
            human_abort=False,
        )

    return _observe


def _human_abort_observer(abort_index: int) -> Observer:
    def _observe(index: int, sample: TrajectorySample) -> TickObservation:
        tick = healthy_tick(sample.positions_rad, sample.velocities_rad_s)
        if index == abort_index:
            return TickObservation(
                status_bytes=tick.status_bytes,
                motor_temps_c=tick.motor_temps_c,
                positions_rad=tick.positions_rad,
                velocities_rad_s=tick.velocities_rad_s,
                human_abort=True,
            )
        return tick

    return _observe


def test_motor_fault_stops_injection() -> None:
    context = build_context(_motor_fault_observer(_ABORT_INDEX))
    result = context.injector.start(_confirmed())
    assert result.status is InjectionStatus.ABORTED
    assert result.cause is AbortCause.MOTOR_FAULT
    assert result.resume_index == _ABORT_INDEX
    assert context.latch.is_active is True


def test_comm_loss_stops_injection() -> None:
    clock = ManualClock()
    context = build_context(_comm_loss_observer(_ABORT_INDEX, clock), clock=clock)
    result = context.injector.start(_confirmed())
    assert result.status is InjectionStatus.ABORTED
    assert result.cause is AbortCause.COMM_LOSS
    assert result.resume_index == _ABORT_INDEX
    assert context.latch.is_active is True


def test_over_temperature_stops_injection() -> None:
    context = build_context(_over_temp_observer(_ABORT_INDEX))
    result = context.injector.start(_confirmed())
    assert result.status is InjectionStatus.ABORTED
    assert result.cause is AbortCause.OVER_TEMPERATURE
    assert result.resume_index == _ABORT_INDEX
    assert context.latch.is_active is True


def test_joint_limit_stops_injection() -> None:
    context = build_context(_joint_limit_observer(_ABORT_INDEX))
    result = context.injector.start(_confirmed())
    assert result.status is InjectionStatus.ABORTED
    assert result.cause is AbortCause.JOINT_LIMIT
    assert result.resume_index == _ABORT_INDEX
    assert context.latch.is_active is True


def test_human_abort_stops_injection() -> None:
    context = build_context(_human_abort_observer(_ABORT_INDEX))
    result = context.injector.start(_confirmed())
    assert result.status is InjectionStatus.ABORTED
    assert result.cause is AbortCause.HUMAN_ABORT
    assert result.resume_index == _ABORT_INDEX
    assert context.latch.is_active is True


def test_abort_stops_before_commanding_the_abort_tick() -> None:
    # The stream stops at the abort index: everything before it was commanded, nothing at
    # or after it — the abort genuinely bit rather than being recorded post hoc.
    context = build_context(_human_abort_observer(_ABORT_INDEX))
    context.injector.start(_confirmed())
    assert context.torque_path is not None
    assert context.torque_path.commanded_indices == list(range(_ABORT_INDEX))
