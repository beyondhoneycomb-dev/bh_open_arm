"""Startup proof that the self-collision (arm-arm) pair test is actually live (③).

A preflight that always returns "no collision" because the collision engine is disabled is
worse than none: it is a green that means nothing. `02b` WP-2C-08 makes an inactive
self-collision pair a `FAIL_BLOCKING` for exactly that reason — a silently vacuous check.

Two proofs run at startup:

  * static — every collision geom carries a non-zero contype AND a non-zero conaffinity, so
    it can both emit and receive a contact. A geom with either bitmask zeroed is invisible
    to one side of every pair test.
  * dynamic (the positive control) — a known in-range configuration that overlaps the two
    arms must yield at least one contact between a left-arm geom and a right-arm geom. If a
    configuration engineered to collide produces no arm-arm contact, the pair test is off.

The dynamic proof is the load-bearing one: a model could pass the static check and still
exclude every arm-arm pair. It falls back to a seeded in-range search only if the primary
known configuration does not collide, so a benign geometry tweak does not read as a
disabled engine while a genuinely disabled engine still fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.collision_preflight.constants import (
    KNOWN_ARM_ARM_COLLISION_LEFT,
    KNOWN_ARM_ARM_COLLISION_RIGHT,
)
from backend.collision_preflight.model import PreflightModel, geom_arm_side

# The seeded fallback search: how many in-range samples to try before concluding the pair
# test is dead. The seed is fixed so the verdict is reproducible run to run.
_FALLBACK_SEARCH_SAMPLES = 1024
_FALLBACK_SEARCH_SEED = 0


class SelfCollisionInactiveError(Exception):
    """Raised when the arm-arm collision pair test is not live (`02b` WP-2C-08 → FAIL_BLOCKING).

    Either a collision geom cannot participate in a contact (a zeroed bitmask), or no
    configuration — not even one engineered to overlap the arms — produces an arm-arm
    contact. In both cases the preflight would pass every trajectory vacuously.
    """


@dataclass(frozen=True)
class SelfCollisionActivation:
    """Evidence that the arm-arm pair test is live (`02b` WP-2C-08 ③).

    Attributes:
        collidable_geom_count: Collision geoms verified to carry non-zero contype and
            conaffinity.
        probe: How the positive control was satisfied — "known" or "search".
        arm_arm_contact_count: Arm-arm contacts the satisfying configuration produced.
        sample_pair: One `(geom1_name, geom2_name)` arm-arm contact, as proof.
    """

    collidable_geom_count: int
    probe: str
    arm_arm_contact_count: int
    sample_pair: tuple[str, str]

    def as_record(self) -> dict[str, Any]:
        """Render the activation evidence for an artifact.

        Returns:
            (dict[str, Any]) Every field of the evidence.
        """
        return {
            "collidable_geom_count": self.collidable_geom_count,
            "probe": self.probe,
            "arm_arm_contact_count": self.arm_arm_contact_count,
            "sample_pair": list(self.sample_pair),
        }


def assert_collision_geoms_collidable(model: PreflightModel) -> int:
    """Refuse a model whose collision geoms cannot participate in a contact (static ③).

    Args:
        model: The loaded preflight model.

    Returns:
        (int) The number of collision geoms verified collidable.

    Raises:
        SelfCollisionInactiveError: If any collision geom has a zero contype or conaffinity.
    """
    for geom_id in model.collision_geom_ids:
        contype, conaffinity = model.geom_contype_conaffinity(geom_id)
        if contype == 0 or conaffinity == 0:
            raise SelfCollisionInactiveError(
                f"collision geom {model.geom_name(geom_id)!r} has contype={contype} "
                f"conaffinity={conaffinity}; it cannot participate in a contact, so the "
                "self-collision check is vacuous (02b WP-2C-08 → FAIL_BLOCKING)"
            )
    return len(model.collision_geom_ids)


def _arm_arm_contacts(model: PreflightModel, qpos: tuple[float, ...]) -> list[tuple[str, str]]:
    """Return the arm-arm collision geom pairs at a configuration.

    Args:
        model: The loaded preflight model.
        qpos: A full-model configuration.

    Returns:
        (list[tuple[str, str]]) Each contact between a left-arm and a right-arm geom, by name.
    """
    data = model.forward(qpos)
    pairs: list[tuple[str, str]] = []
    for index in range(int(data.ncon)):
        contact = data.contact[index]
        name1 = model.geom_name(int(contact.geom1))
        name2 = model.geom_name(int(contact.geom2))
        side1 = geom_arm_side(name1)
        side2 = geom_arm_side(name2)
        if side1 and side2 and side1 != side2:
            pairs.append((name1, name2))
    return pairs


def assert_self_collision_active(model: PreflightModel) -> SelfCollisionActivation:
    """Prove the arm-arm pair test is live, statically and by positive control (③).

    Args:
        model: The loaded preflight model.

    Returns:
        (SelfCollisionActivation) The activation evidence.

    Raises:
        SelfCollisionInactiveError: If a geom is non-collidable, or no configuration
            produces an arm-arm contact (`02b` WP-2C-08 → FAIL_BLOCKING).
    """
    collidable = assert_collision_geoms_collidable(model)

    known = model.qpos_from_arms(KNOWN_ARM_ARM_COLLISION_LEFT, KNOWN_ARM_ARM_COLLISION_RIGHT)
    pairs = _arm_arm_contacts(model, known)
    if pairs:
        return SelfCollisionActivation(
            collidable_geom_count=collidable,
            probe="known",
            arm_arm_contact_count=len(pairs),
            sample_pair=pairs[0],
        )

    rng = np.random.default_rng(_FALLBACK_SEARCH_SEED)
    for _ in range(_FALLBACK_SEARCH_SAMPLES):
        pairs = _arm_arm_contacts(model, model.random_configuration(rng))
        if pairs:
            return SelfCollisionActivation(
                collidable_geom_count=collidable,
                probe="search",
                arm_arm_contact_count=len(pairs),
                sample_pair=pairs[0],
            )

    raise SelfCollisionInactiveError(
        "no configuration produced an arm-arm contact, not even one engineered to overlap "
        f"the arms nor {_FALLBACK_SEARCH_SAMPLES} in-range samples; the self-collision pair "
        "test is not live (02b WP-2C-08 → FAIL_BLOCKING)"
    )
