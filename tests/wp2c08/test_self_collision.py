"""Acceptance ③: arm-arm contact is computed at startup; a dead pair test is FAIL_BLOCKING."""

from __future__ import annotations

import numpy as np
import pytest

from backend.collision_preflight import selfcollision
from backend.collision_preflight.model import PreflightModel, geom_arm_side
from backend.collision_preflight.selfcollision import (
    SelfCollisionInactiveError,
    assert_collision_geoms_collidable,
    assert_self_collision_active,
)
from backend.safety_bringup.constants import COLLISION_MARGIN_DEFAULT_M


def test_arm_arm_contact_is_computed(preflight_model: PreflightModel) -> None:
    activation = assert_self_collision_active(preflight_model)
    assert activation.arm_arm_contact_count > 0
    assert activation.collidable_geom_count == len(preflight_model.collision_geom_ids)
    # The sample proof is a genuine left/right cross contact.
    side1 = geom_arm_side(activation.sample_pair[0])
    side2 = geom_arm_side(activation.sample_pair[1])
    assert {side1, side2} == {"left", "right"}


def test_known_probe_is_enough(preflight_model: PreflightModel) -> None:
    # On the committed asset the hardcoded positive control collides, so no search is needed.
    assert assert_self_collision_active(preflight_model).probe == "known"


def test_noncollidable_geom_is_fail_blocking() -> None:
    model = PreflightModel(COLLISION_MARGIN_DEFAULT_M)
    # Zero one collision geom's conaffinity: it can no longer receive a contact, so the
    # self-collision check would be silently vacuous for every pair it belongs to.
    first_geom = model.collision_geom_ids[0]
    model._model.geom_conaffinity[first_geom] = 0  # noqa: SLF001 — injecting the fault under test
    with pytest.raises(SelfCollisionInactiveError):
        assert_collision_geoms_collidable(model)
    with pytest.raises(SelfCollisionInactiveError):
        assert_self_collision_active(model)


def test_no_arm_arm_contact_anywhere_is_fail_blocking(
    preflight_model: PreflightModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A model that passes the static check but never produces an arm-arm contact — the pair
    # test is excluded rather than bitmask-disabled — must still FAIL_BLOCKING.
    monkeypatch.setattr(selfcollision, "_arm_arm_contacts", lambda model, qpos: [])
    with pytest.raises(SelfCollisionInactiveError):
        assert_self_collision_active(preflight_model)


def test_fallback_search_finds_a_collision(
    preflight_model: PreflightModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force the known probe to miss by pointing it at the neutral pose (no arm-arm contact);
    # the seeded in-range search must still find a collision on the committed asset, so a
    # benign geometry tweak does not read as a dead engine.
    neutral = tuple(np.zeros(7))
    monkeypatch.setattr(selfcollision, "KNOWN_ARM_ARM_COLLISION_LEFT", neutral)
    monkeypatch.setattr(selfcollision, "KNOWN_ARM_ARM_COLLISION_RIGHT", neutral)
    activation = assert_self_collision_active(preflight_model)
    assert activation.probe == "search"
    assert activation.arm_arm_contact_count > 0
