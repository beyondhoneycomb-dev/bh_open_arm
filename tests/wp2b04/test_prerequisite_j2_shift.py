"""The §2.0 J2 +pi/2 prerequisite is material to the payload-reflected shoulder gravity.

WP-2B-02 discharges the joint2 +pi/2 shift at model load; this test confirms the prerequisite
matters for the payload path too. Feeding a v1 joint2 angle without WP-2B-01's shift versus
with it (via `convert_joint2_angle`, WP-2B-01's declared API) moves the payload-reflected
shoulder gravity by more than the payload's own torque — the sin<->cos error the shift exists
to prevent. A payload model that ignored the convention would carry that error as a permanent
residual offset.
"""

from __future__ import annotations

from backend.dynamics.converter import convert_joint2_angle
from backend.payload import Payload


def test_j2_shift_moves_payload_reflected_shoulder_gravity(right_model) -> None:
    v1_joint2 = 0.0  # a v1 zero-convention shoulder angle
    v2_joint2 = convert_joint2_angle(v1_joint2)  # the same pose in the v2 convention
    assert abs(v2_joint2 - v1_joint2) > 1.0  # a ~pi/2 move, not a rounding difference

    right_model.registry.register(Payload.at_mount(3.0, "tool"))
    without_shift = right_model.tau_grav((0.0, v1_joint2, 0.0, 0.0, 0.0, 0.0, 0.0))
    with_shift = right_model.tau_grav((0.0, v2_joint2, 0.0, 0.0, 0.0, 0.0, 0.0))

    # The shoulder gravity term differs by more than a newton-metre — the shift is material.
    assert abs(with_shift[1] - without_shift[1]) > 1.0
