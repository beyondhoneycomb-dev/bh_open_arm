"""A dummy robot fixture: position-only commands in, a 48-dim observation out.

`02b` §5.2 WP-3A-06 and Wave 0-C dummy mode: 3B drives a robot it does not have,
so this stand-in accepts the same action the safety gate would send to CAN and
returns the same `observation.state` the recorder would log — with no CAN, no
motors, no hardware.

The action it accepts is the `CTR-PRIM@v1` position-only payload: `<motor>.pos`
in degrees, 8 keys single-arm or 16 bimanual, and never a `.vel`/`.torque`
dimension (rejecting those is the FAIL_BLOCKING rule `CTR-REC@v1` also enforces).
The observation it returns is the interleaved `CTR-REC@v1` `observation.state`
vector — 48-wide for a bimanual robot recording velocity and torque. Every shape
and name is imported from the frozen contracts; none is restated here.
"""

from __future__ import annotations

from collections.abc import Mapping

from contracts.prim import ACTION_POSITION_UNIT
from contracts.recorder import (
    POSITION_SUFFIX,
    TORQUE_SUFFIX,
    VELOCITY_SUFFIX,
    action_dim,
    action_names,
    motor_keys,
    observation_state_names,
)

# The fraction of the remaining position error the measured joint closes each
# step. A first-order approach makes the measured velocity a deterministic,
# non-zero function of the command, so an observation test sees real motion
# rather than a pure echo. Chosen once here; it is a fixture dynamic, not a
# controller gain the real robot uses.
_APPROACH_FRACTION = 0.5

# The control period in seconds the fixture integrates over, so velocity is in
# the contract's degrees-per-second. One tick is one recorded frame.
_STEP_SECONDS = 0.02

# A dummy has no torque sensor; every torque channel reads a deterministic zero.
_DUMMY_TORQUE = 0.0


class DummyRobot:
    """A stateful, deterministic robot stand-in over the frozen action/observation shapes.

    The robot holds a measured position and velocity per motor. `step` applies a
    position-only action, advances the first-order dynamics one control tick, and
    returns the resulting observation. State and outputs are a pure function of the
    command history, so a 3B integration test is reproducible.
    """

    def __init__(self, bimanual: bool, use_velocity_and_torque: bool) -> None:
        """Initialise a robot at the zero pose.

        Args:
            bimanual: Two arms (16 motors) when True, one (8) when False.
            use_velocity_and_torque: Whether the observation carries `.vel`/`.torque`
                channels; the action width never changes with this switch.
        """
        self.mBimanual = bimanual
        self.mUseVelocityAndTorque = use_velocity_and_torque
        self.mMotorKeys = motor_keys(bimanual)
        self.mPositions = dict.fromkeys(self.mMotorKeys, 0.0)
        self.mVelocities = dict.fromkeys(self.mMotorKeys, 0.0)

    def action_features(self) -> dict[str, type]:
        """The flat `{<motor>.pos: float}` action feature map (`CTR-TEL@v1` convention).

        Returns:
            (dict[str, type]) One `float` entry per position channel.
        """
        return dict.fromkeys(action_names(self.mBimanual), float)

    def action_names(self) -> tuple[str, ...]:
        """The position-only action channel names, in dataset order."""
        return action_names(self.mBimanual)

    def action_dim(self) -> int:
        """The action width (8 single / 16 bimanual), independent of the vel/torque switch."""
        return action_dim(self.mBimanual)

    def observation_state_names(self) -> tuple[str, ...]:
        """The interleaved `observation.state` names (48-wide for bimanual + vel/torque)."""
        return observation_state_names(self.mBimanual, self.mUseVelocityAndTorque)

    def position_unit(self) -> str:
        """The action/position unit, from `CTR-PRIM@v1` (degrees)."""
        return ACTION_POSITION_UNIT

    def _validate_action(self, action: Mapping[str, float]) -> None:
        """Reject an action that is not exactly the position-only channel set.

        Args:
            action: The commanded action.

        Raises:
            ValueError: If a `.vel`/`.torque` channel is present, or the key set is
                not the exact position-only set for this arm count.
        """
        poisoned = [key for key in action if key.endswith((VELOCITY_SUFFIX, TORQUE_SUFFIX))]
        if poisoned:
            raise ValueError(
                f"action carries non-position channels {poisoned}; the action is the position "
                "command sent to CAN, never a .vel/.torque value (CTR-REC@v1 FAIL_BLOCKING)"
            )
        if set(action) != set(self.action_names()):
            raise ValueError(
                f"action keys {sorted(action)} are not the position-only set "
                f"{list(self.action_names())}"
            )

    def step(self, action: Mapping[str, float]) -> dict[str, object]:
        """Apply a position-only action, advance one tick, and return the observation.

        Args:
            action: `<motor>.pos` degrees for every motor.

        Returns:
            (dict[str, object]) `{observation.state: tuple[float, ...]}` plus the
                per-channel names, sized to `observation_state_names`.
        """
        self._validate_action(action)
        for motor in self.mMotorKeys:
            target = float(action[f"{motor}{POSITION_SUFFIX}"])
            previous = self.mPositions[motor]
            updated = previous + _APPROACH_FRACTION * (target - previous)
            self.mVelocities[motor] = (updated - previous) / _STEP_SECONDS
            self.mPositions[motor] = updated
        return self.observation()

    def observation(self) -> dict[str, object]:
        """Return the current observation in the frozen `observation.state` shape.

        Returns:
            (dict[str, object]) The interleaved state vector and its channel names.
        """
        names = self.observation_state_names()
        return {"observation.state": self._state_vector(), "names": names}

    def _state_vector(self) -> tuple[float, ...]:
        """Build the interleaved `observation.state` vector from measured state.

        Returns:
            (tuple[float, ...]) Per-motor `(pos[, vel, torque])`, arm-major, length
                equal to `len(observation_state_names)`.
        """
        values: list[float] = []
        for motor in self.mMotorKeys:
            values.append(round(self.mPositions[motor], 9))
            if self.mUseVelocityAndTorque:
                values.append(round(self.mVelocities[motor], 9))
                values.append(_DUMMY_TORQUE)
        return tuple(values)

    def zero_action(self) -> dict[str, float]:
        """A valid all-zero position action, for a test that needs a neutral command.

        Returns:
            (dict[str, float]) `<motor>.pos` -> 0.0 for every motor.
        """
        return dict.fromkeys(self.action_names(), 0.0)
