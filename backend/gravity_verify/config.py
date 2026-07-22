"""The verification run configuration and the FR-SAF-072 torque-availability gate.

`use_velocity_and_torque` is the follower/leader recording switch
(`packages/lerobot_robot_openarm/config_oa.py`, default False). WP-2B-03 reads it as an input;
it does not own or set it. The one thing this module enforces is the coupling FR-SAF-072 /
spec 09 FR-SIM-025b state: with the switch off there is no `.torque` channel, so `tau_meas`
does not exist and the residual verification is refused rather than run against a fabricated
measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.gravity.backend import Arm
from backend.gravity.constants import GRAVITY_SCALE_DEFAULT
from backend.gravity_verify.errors import VerificationRefusedError


@dataclass(frozen=True)
class VerificationConfig:
    """The inputs a verification run is parameterised by.

    Attributes:
        use_velocity_and_torque: The follower recording switch, mirrored from the OpenArm
            follower config. False means no measured torque, which the run refuses.
        arm: Which follower arm the model is evaluated for; the right arm is the WP-2B-01
            reference arm the v2 convention was frozen against.
        gravity_scale: The gravity trim the modelled torque is computed with, in `[0, 1.2]`.
            Kept at 1.0 for verification so the residual reflects the full modelled gravity,
            not a trimmed one.
    """

    use_velocity_and_torque: bool
    arm: Arm = Arm.RIGHT
    gravity_scale: float = GRAVITY_SCALE_DEFAULT

    def require_torque_measurement(self) -> None:
        """Refuse the run when torque measurement is unavailable (FR-SAF-072, acceptance ③).

        Raises:
            VerificationRefusedError: If `use_velocity_and_torque` is False. The refusal is the
                contract: verification execution is refused, not degraded to a warning, because
                there is no measured torque to form a residual against.
        """
        if not self.use_velocity_and_torque:
            raise VerificationRefusedError(
                "gravity-model verification needs a measured joint torque, but "
                "use_velocity_and_torque is false so the follower carries no .torque channel "
                "(spec 12 §2.15 / FR-SIM-025b); the run is refused (FR-SAF-072, WP-2B-03 ③)"
            )
