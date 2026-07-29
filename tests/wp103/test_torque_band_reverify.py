"""The rig measurement the torque band is owed before a non-zero tau is ever commanded.

`FEEDFORWARD_TORQUE_LIMIT_NM` is built from spec figures — the URDF effort table via
`backend.threshold.constants` — and nothing in this repo has read a torque limit off a
motor. That gap is not hypothetical on this bench: DM4340's V_MAX was registered as 8.0
and measured 10.0, and a packet-scale constant being wrong by a ratio skews every command
through it silently. A torque ceiling can be wrong the same way, and a wrong ceiling is a
refusal band that admits more than the joint can take.

So the band is offline-verified only: the tests beside this one prove that a value outside
it is refused and a value inside it is routed unaltered, which is a statement about the
code, not about the hardware. The measurement itself needs a person, a powered bus, and the
CAN adapter — none of which a test process has.

Unskip when the per-motor limits have been read off the rig and recorded:

    openarm-can-cli show_param --id N     # RID 23 = TMAX, RID 22 = VMAX, RID 21 = PMAX

on all seven ids of both arms, at which point the assertion below becomes a comparison
against the recorded figures rather than a restatement of the spec table it came from.
`03` §5 Q-1 already names J7's TMAX as an open bench check for exactly this reason.
"""

from __future__ import annotations

import pytest

_RIG_MEASUREMENT_PENDING = (
    "per-motor TMAX (RID 23) has not been read off either arm; the refusal band is the spec "
    "effort table, and asserting it as a hardware fact offline would be a faked green"
)


@pytest.mark.skip(reason=_RIG_MEASUREMENT_PENDING)
def test_the_effort_band_matches_the_motors_own_torque_limits() -> None:
    # Once measured: every entry of FEEDFORWARD_TORQUE_LIMIT_NM must be at or below the TMAX
    # its motor reports, per arm, so the band this command path refuses outside is bounded by
    # what the hardware itself declares rather than by a table that was transcribed. Reading
    # it needs a powered bus and the PEAK PCAN adapter, so it is an operator step and not a
    # fixture one.
    raise AssertionError("unreachable: skipped until the per-motor limits are read off the rig")
