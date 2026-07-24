"""Shared fixtures for the WP-4B-01 matrix-engine tests (`02c` §2.1).

Observation configurations are built from the frozen `CTR-REC@v1` channel-name
builders (`contracts.recorder`), never re-spelt here, so a change to the recorder
grammar reaches these tests. The 48-dim bimanual case is additionally checked
against the committed WP-4A-02 `derive_observation_config` reading the committed
synthetic dataset, proving the engine is exercised on the same observation config
the training band produces, not a bespoke one.
"""

from __future__ import annotations

from backend.training.preflight import ObservationConfig
from contracts.recorder import action_names, observation_state_names


def observation_config(bimanual: bool, use_velocity_and_torque: bool) -> ObservationConfig:
    """Build an observation config from the frozen recorder channel names.

    Args:
        bimanual: True for the two-arm (48/16) layout, False for single-arm (24/8).
        use_velocity_and_torque: True for the full pos/vel/torque state, False for
            the position-only state.

    Returns:
        (ObservationConfig) The configuration for the requested layout, with its
            canonical `names` so a `.pos` projection selects by suffix.
    """
    names = tuple(observation_state_names(bimanual, use_velocity_and_torque))
    return ObservationConfig(
        use_velocity_and_torque=use_velocity_and_torque,
        state_dim=len(names),
        action_dim=len(action_names(bimanual)),
        names=names,
        bimanual=bimanual,
    )


def bimanual_full() -> ObservationConfig:
    """Return the 48-dim bimanual velocity-and-torque configuration."""
    return observation_config(bimanual=True, use_velocity_and_torque=True)


def single_arm_full() -> ObservationConfig:
    """Return the 24-dim single-arm velocity-and-torque configuration."""
    return observation_config(bimanual=False, use_velocity_and_torque=True)
