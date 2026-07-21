"""The raw observation channel: 48 dims preserved, plus the CAN drop counter.

`rawObservation` keeps every observation.state channel (16 D-8): the bimanual
follower flattens 8 motors x 2 arms x {pos, vel, torque} into 48 dims, mixing
`Deg`, `DegPerSec` and `Nm`. This module does not re-declare that layout — it
reuses the frozen CTR-UNIT `observation_state` map so the per-index units have one
owner (contracts/unit_tags.yaml). It adds the one thing LeRobot does not export:
the CAN packet drop counter, surfaced as observation meta (01 FR-SYS-018) because
`_batch_refresh` reuses the last known state on a drop and only logs a warning.
"""

from __future__ import annotations

from contracts.units import ObservationChannel, expected_dim, observation_state_units

# The bimanual observation.state width the schema asserts (16 D-8, 10 §2.3).
BIMANUAL_OBSERVATION_DIM = 48
SINGLE_ARM_OBSERVATION_DIM = 24

# CAN packet-drop counter exposed as observation meta (01 FR-SYS-018). It is a
# count, not a physical quantity, so it carries no CTR-UNIT tag; it rides beside
# the 48 tagged channels rather than inside them.
DROP_COUNTER_META = "can_packet_drop_count"


def raw_observation_channels(bimanual: bool = True) -> tuple[ObservationChannel, ...]:
    """Return the ordered, unit-tagged observation channels, all preserved.

    Args:
        bimanual: Whether to build the 48-dim bimanual layout or 24-dim single arm.

    Returns:
        (tuple[ObservationChannel, ...]) One entry per index, each carrying the
        CTR-UNIT tag for that channel (Deg / DegPerSec / Nm).
    """
    return observation_state_units(bimanual=bimanual)


def raw_observation_dim(bimanual: bool = True) -> int:
    """Return the declared observation.state width for the arm configuration.

    Args:
        bimanual: Whether to report the bimanual (48) or single-arm (24) width.

    Returns:
        (int) The frozen dimension, sourced from contracts/unit_tags.yaml.
    """
    return expected_dim(bimanual=bimanual)
