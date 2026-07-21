"""Acceptance 8: a torque clamp requires Nm, not a packet-scale value.

`03` FR-MOT-037 clamps torque in newton-metres, a different axis from the DM T_MAX
packet scale. Passing a `PacketTorque` to a clamp that requires `Nm` is a static
type error. Expected error code: [arg-type].
"""

from __future__ import annotations

from contracts.units import Nm, PacketTorque, clamp_torque

clamped = clamp_torque(PacketTorque(30000), Nm(54.0))
