"""CG-2B-10a — a write to the seed profile is refused (FR-SAF-031).

Read-only is proven at every level a write could be attempted: the store's write method, the
frozen profile object, the read-only payload view, and the copy-on-read accessors.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from backend.dynamics.provenance import Provenance
from backend.seed_profile.constants import SEED_ROBOT_VERSION
from backend.seed_profile.errors import SeedProfileError, SeedWriteRefusedError
from backend.seed_profile.profile import SeedProfile
from backend.seed_profile.store import SeedProfileStore
from tests.wp2b10.conftest import make_v2_provenance


def test_store_save_is_refused(store: SeedProfileStore, seed: SeedProfile) -> None:
    """The store refuses to persist the seed — the acceptance-① write refusal."""
    with pytest.raises(SeedWriteRefusedError, match="read-only"):
        store.save(seed)


def test_store_save_does_not_touch_disk(store: SeedProfileStore, seed: SeedProfile) -> None:
    """A refused save leaves the on-disk asset byte-for-byte unchanged."""
    before = store.asset_path.read_bytes()
    with pytest.raises(SeedWriteRefusedError):
        store.save(seed)
    assert store.asset_path.read_bytes() == before


def test_profile_object_is_frozen(seed: SeedProfile) -> None:
    """The profile's fields cannot be rebound."""
    with pytest.raises(FrozenInstanceError):
        seed.provenance = make_v2_provenance()  # type: ignore[misc]


def test_payload_top_level_is_read_only(seed: SeedProfile) -> None:
    """The payload view refuses top-level key assignment."""
    with pytest.raises(TypeError):
        seed.payload["seed_pose_rad"] = [0.0] * 7  # type: ignore[index]


def test_seed_pose_accessor_returns_independent_copy(seed: SeedProfile) -> None:
    """Mutating a returned pose cannot reach back into the seed."""
    pose = list(seed.seed_pose())
    pose[1] = 999.0
    assert seed.seed_pose()[1] != 999.0


def test_as_v1_mapping_is_an_independent_copy(seed: SeedProfile) -> None:
    """Mutating the exported v1 mapping cannot reach back into the seed."""
    mapping = seed.as_v1_mapping()
    mapping["seed_pose_rad"][0] = 999.0
    mapping["provenance"]["robot_version"] = "2.0"
    assert seed.seed_pose()[0] != 999.0
    assert seed.provenance.robot_version == SEED_ROBOT_VERSION


def test_v2_stamped_seed_is_refused() -> None:
    """A 'seed' carrying a v2 stamp is a category error and is refused (FR-SAF-031)."""
    raw = {
        "provenance": make_v2_provenance().to_dict(),
        "seed_pose_rad": [0.0] * 7,
    }
    with pytest.raises(SeedProfileError, match="v1 origin"):
        SeedProfile.from_mapping(raw)


def test_seed_without_provenance_is_refused() -> None:
    """A seed asset with no provenance cannot be isolated and is refused."""
    with pytest.raises(SeedProfileError, match="no provenance"):
        SeedProfile.from_mapping({"seed_pose_rad": [0.0] * 7})


def test_loaded_seed_is_v1(seed: SeedProfile) -> None:
    """The shipped seed loads as robot_version '1.0'."""
    assert isinstance(seed.provenance, Provenance)
    assert seed.provenance.robot_version == SEED_ROBOT_VERSION
    assert not seed.provenance.is_v2()
