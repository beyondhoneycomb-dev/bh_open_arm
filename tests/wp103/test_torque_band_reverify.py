"""The feed-forward torque band, checked against the TMAX the motors themselves report.

`FEEDFORWARD_TORQUE_LIMIT_NM` is the ceiling the torque command path refuses above, and it
is built from the URDF effort table (`backend.threshold.constants`). A ceiling transcribed
from a table can be wrong the way DM4340's V_MAX was wrong: registered 8.0, measured 10.0.
A packet-scale constant off by a ratio skews every command through it silently, and a torque
ceiling set above what the joint's encoding can even represent is a refusal band that admits
more than the motor can take.

The motors' own RID 23 (TMAX) is the external bound. It is read by the `WP-0B-07` probe and
lands in the same capture directory the RID cross-check consumes, so this re-verification
reuses that capture rather than defining a second source for the same bytes. Absent a
capture the check skips with a reason (`02a` §4.1) — the band's *offline* properties (a
value outside it is refused, a value inside it is routed unaltered) are proven by the tests
beside this one, which are statements about the code and make no claim about hardware.

The gripper is excluded: the band's eighth entry is `None` (no ceiling) and the rig carries
no motor on `0x08`.
"""

from __future__ import annotations

import pytest

from backend.can.rid.dump import load_dump
from backend.can.rid.registers import RID_TMAX
from backend.can.rid.reverify import FIXTURE_ENV_VAR, fixture_dir_from_env
from backend.endeffector import ARM_JOINT_SEND_IDS, SIDES
from backend.threshold.constants import N_ARM_JOINTS
from packages.lerobot_robot_openarm.openarm_follower_oa import FEEDFORWARD_TORQUE_LIMIT_NM

_REAL_FIXTURE = fixture_dir_from_env()

_SKIP_REASON = (
    "per-motor TMAX (RID 23) needs a real RID capture: read it with "
    "`openarm-can-cli show_param -c N -r 23` on every fitted id of both arms and set "
    f"{FIXTURE_ENV_VAR} to the capture directory; asserting the band as a hardware fact "
    "without one would be a faked green"
)

# The band's arm entries, paired with the send id whose TMAX bounds each. The eighth entry is
# the gripper's `None`, and slicing it off here is what keeps an absent motor out of the check.
_ARM_BAND_NM = FEEDFORWARD_TORQUE_LIMIT_NM[:N_ARM_JOINTS]


@pytest.mark.skipif(_REAL_FIXTURE is None, reason=_SKIP_REASON)
def test_the_effort_band_matches_the_motors_own_torque_limits() -> None:
    assert _REAL_FIXTURE is not None
    dump_files = sorted(_REAL_FIXTURE.glob("*.json"))
    # A directory that holds no dump would leave every loop below iterating nothing and the
    # test green having read no bytes at all.
    assert dump_files, f"{_REAL_FIXTURE} holds no *.json RID capture"
    # One capture per arm. A single-arm capture satisfies every per-joint assertion while
    # saying nothing about the other arm's wrist, which is the joint with the least headroom.
    assert len(dump_files) == len(SIDES), (
        f"{_REAL_FIXTURE} holds {len(dump_files)} capture(s); the band is bounded per arm and "
        f"the rig has {len(SIDES)} ({', '.join(SIDES)})"
    )

    compared = 0
    for path in dump_files:
        dump = load_dump(path)
        for ceiling_nm, send_id in zip(_ARM_BAND_NM, ARM_JOINT_SEND_IDS, strict=True):
            # A capture missing the motor, or missing RID 23 on it, is a capture that cannot
            # bound this joint. Refused by name rather than skipped past, because skipping it
            # is what turns an unread register into a passing joint.
            assert send_id in dump.motors, f"{path.name}: no motor 0x{send_id:02X} in the capture"
            motor = dump.motors[send_id]
            assert motor.has(RID_TMAX), (
                f"{path.name}: motor 0x{send_id:02X} carries no RID {RID_TMAX} (TMAX)"
            )
            measured_tmax_nm = float(motor.decoded(RID_TMAX).value)
            assert ceiling_nm is not None
            assert ceiling_nm <= measured_tmax_nm, (
                f"{path.name}: motor 0x{send_id:02X} reports TMAX {measured_tmax_nm} Nm but the "
                f"feed-forward band admits up to {ceiling_nm} Nm; a ceiling above the motor's "
                "own torque scale is a refusal band that admits more than the joint can take"
            )
            compared += 1

    assert compared == len(dump_files) * N_ARM_JOINTS, (
        f"compared {compared} joint(s); expected {len(dump_files)} arm(s) x {N_ARM_JOINTS}"
    )
