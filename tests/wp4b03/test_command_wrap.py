"""CG-4B-03f — a commanded position beyond +/-12.5 rad is refused (wrap defence).

FR-INF-038: every Damiao motor encodes position over +/-PMAX = 12.5 rad. A command
past it does not saturate — the field wraps to the opposite end, a large silent jump —
so the guard refuses instead of letting it through. PMAX is read from the committed
`MOTOR_LIMIT_PARAMS`, not restated here.
"""

from __future__ import annotations

from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType
from backend.inference.load_preflight import (
    JOINT_MOTORS,
    command_within_pmax,
    pmax_rad,
)


def test_command_over_pmax_is_refused() -> None:
    """CG-4B-03f: |command| > 12.5 rad -> refused."""
    command = [0.0] * len(JOINT_MOTORS)
    command[3] = 13.0  # past +12.5 rad

    verdict = command_within_pmax(command)

    assert not verdict.ok
    assert verdict.offenders[0][0] == 3
    assert verdict.offenders[0][2] == 12.5


def test_negative_command_over_pmax_is_refused() -> None:
    """The wrap guard is on magnitude: a command below -12.5 rad is refused too."""
    command = [0.0] * len(JOINT_MOTORS)
    command[0] = -12.6

    verdict = command_within_pmax(command)

    assert not verdict.ok


def test_command_within_pmax_is_allowed() -> None:
    """A command at the +/-12.5 boundary is in range (the guard is not vacuous)."""
    command = [12.5, -12.5, 0.0, 1.0, -1.0, 5.0, -5.0, 0.0]

    verdict = command_within_pmax(command)

    assert verdict.ok
    assert verdict.offenders == ()


def test_pmax_is_read_from_motor_table() -> None:
    """PMAX is the committed MOTOR_LIMIT_PARAMS p_max (12.5 for every arm motor)."""
    assert pmax_rad(MotorType.DM8009) == MOTOR_LIMIT_PARAMS[MotorType.DM8009].p_max == 12.5
    assert pmax_rad(MotorType.DM4340) == 12.5
    assert pmax_rad(MotorType.DM4310) == 12.5


def test_bimanual_command_width_is_supported() -> None:
    """A 16-wide bimanual command is checked per joint against its motor's PMAX."""
    command = [0.0] * 16
    command[11] = 20.0

    verdict = command_within_pmax(command)

    assert not verdict.ok
    assert verdict.offenders[0][0] == 11
