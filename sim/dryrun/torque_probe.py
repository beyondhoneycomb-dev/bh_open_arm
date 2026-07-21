"""FR-SIM-133 demonstration: the torque check is inert on implicit actuators.

Acceptance ⑥ requires *showing*, not asserting, that torque check ③ silently
passes on an implicit actuator, then re-showing that the measured/inverse path
catches the same over-torque. This module builds the minimal case that makes the
trap concrete: a single hinge holding a heavy lever against gravity, actuated by a
position actuator clamped to ``forcerange = ±limit``.

At that pose the joint truly demands far more than the limit to hold, but:

- The **implicit** effort ``qfrc_actuator`` is clipped to ``±limit`` by the
  actuator, so a torque check reading it sees ``|τ| ≤ limit`` and passes — inert.
- The **measured** effort from inverse dynamics (``qfrc_inverse`` at zero
  acceleration) is the true holding torque, which exceeds the limit — detected.

``demonstrate`` returns both efforts (as ``Nm``) so a test can run the real
``check_torque_limits`` against each and prove the first finds nothing while the
second finds the violation.
"""

from __future__ import annotations

from dataclasses import dataclass

import mujoco

from contracts.units.tags import Nm

# The probe joint's motor key, used to key both the effort and the limit dicts so
# the real check compares like against like.
PROBE_MOTOR_KEY = "probe_joint"

# A lever heavy and long enough that its gravity holding torque dwarfs any of the
# arm torque limits, so the over-torque is unambiguous on any limit we probe.
_LEVER_MASS_KG = 8.0
_LEVER_LENGTH_M = 0.5

# A commanded target far from the pose, so the position actuator drives to its force
# limit and the clamped reading sits *at* the limit — the clamp masking the demand
# is then visible, not hidden behind a zero command.
_SATURATING_TARGET_RAD = 3.0

_PROBE_XML = """
<mujoco>
  <option gravity="0 0 -9.81"/>
  <worldbody>
    <body name="lever" pos="0 0 1">
      <joint name="probe_joint" type="hinge" axis="0 1 0" limited="true" range="-3.1416 3.1416"/>
      <geom type="capsule" fromto="0 0 0 {length} 0 0" size="0.02" mass="{mass}"/>
    </body>
  </worldbody>
  <actuator>
    <position name="probe_ctrl" joint="probe_joint" kp="500"
              forcelimited="true" forcerange="-{limit} {limit}"/>
  </actuator>
</mujoco>
"""


@dataclass(frozen=True)
class InertVsMeasured:
    """The two efforts a torque check could read at an over-torque pose.

    Attributes:
        limit_nm: The symmetric torque limit the actuator is clamped to.
        inert_effort_nm: The clamped ``qfrc_actuator`` — the inert source.
        measured_effort_nm: The inverse-dynamics required torque — the honest source.
    """

    limit_nm: Nm
    inert_effort_nm: Nm
    measured_effort_nm: Nm


def demonstrate(limit_nm: Nm) -> InertVsMeasured:
    """Build the over-torque probe and read both effort sources at the pose.

    Args:
        limit_nm: The actuator force limit (and torque bound) to probe against.

    Returns:
        (InertVsMeasured) The clamped and the measured efforts at the holding pose.
    """
    xml = _PROBE_XML.format(length=_LEVER_LENGTH_M, mass=_LEVER_MASS_KG, limit=limit_nm.value)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)

    # Hold the lever horizontal (q = 0) while commanding a far target: the position
    # actuator saturates at its force limit, so the clamped reading sits at the
    # bound while gravity demands far more — the clamp masking the true torque.
    data.qpos[0] = 0.0
    data.ctrl[0] = _SATURATING_TARGET_RAD
    mujoco.mj_forward(model, data)
    inert = float(data.qfrc_actuator[0])

    data.qvel[0] = 0.0
    data.qacc[0] = 0.0
    mujoco.mj_inverse(model, data)
    measured = float(data.qfrc_inverse[0])

    return InertVsMeasured(
        limit_nm=limit_nm,
        inert_effort_nm=Nm(inert),
        measured_effort_nm=Nm(measured),
    )
