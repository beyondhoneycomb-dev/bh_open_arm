"""The real observation schema the dummy must reproduce exactly (WP-0A-02).

The dummy is only useful if its `get_observation()` is byte-for-byte the same
contract a real backend returns: same field names, same scalar types, no
dummy-only field. That contract is not invented here — it is the frozen
`OpenArmRobot.observation_features` (48 tagged channels plus the CAN drop counter),
so this module re-exports it and offers the one thing a consumer needs: a diff of a
returned frame against it.

`observation_field_diff` is the upstream reaction the obs-missing scenario trips: a
recorder or dataset builder validating a frame against the schema rejects a frame
whose field set differs, which is exactly what happens when a sensor drops a
channel. Reusing the frozen feature dict means the dummy and the real follower are
measured against one schema, so a passing dummy proves schema parity, not merely
self-consistency.
"""

from __future__ import annotations

from contracts.plugin.robot_abc import openarm_observation_features

# The frozen real-follower observation feature contract: channel name -> scalar
# type. Built once; the dummy targets exactly this key set and these types.
REAL_OBSERVATION_FEATURES: dict[str, type] = openarm_observation_features(bimanual=True)


def observation_field_diff(frame: dict[str, object]) -> tuple[frozenset[str], frozenset[str]]:
    """Return (missing, extra) field-name sets of a frame against the real schema.

    Args:
        frame: A returned observation frame (LeRobot flat observation dict).

    Returns:
        (tuple[frozenset[str], frozenset[str]]) Fields the schema requires but the
        frame lacks, and fields the frame carries but the schema does not. Both
        empty means field diff 0 — the acceptance ① condition.
    """
    required = frozenset(REAL_OBSERVATION_FEATURES)
    present = frozenset(frame)
    return required - present, present - required


def frame_matches_schema(frame: dict[str, object]) -> bool:
    """Report whether a frame matches the real schema in fields and scalar types.

    Args:
        frame: A returned observation frame.

    Returns:
        (bool) True when no field is missing or extra and every value is an
        instance of the type the schema declares for its channel.
    """
    missing, extra = observation_field_diff(frame)
    if missing or extra:
        return False
    return all(
        isinstance(frame[name], declared) for name, declared in REAL_OBSERVATION_FEATURES.items()
    )
