"""Shared builders for the WP-2B-10 acceptance tests.

The seed under test is the shipped read-only asset (`SeedProfileStore.default()`), so the tests
exercise the real isolation path rather than a hand-built stand-in. The v2 target provenance uses
the same sentinel commit the WP-2B-01 fixtures use — a promotion stamps a genuine v2 origin, and
the sentinel says the converted asset is not yet vendored.
"""

from __future__ import annotations

import pytest

from backend.dynamics.converter import JointFrameConverter
from backend.dynamics.provenance import Provenance
from backend.seed_profile.profile import SeedProfile
from backend.seed_profile.store import SeedProfileStore

V2_SOURCE_REPO = "bh_open_arm"
V2_COMMIT_SHA = "0000000000000000000000000000000000000002"
V2_PATH = "backend/seed_profile/promoted/follower_v2.yaml"
V2_IDENTIFIED_ON = "2026-07-22"


def make_v2_provenance(**overrides: str) -> Provenance:
    """Return a valid v2 target provenance stamp, with any field overridden by keyword."""
    data = {
        "source_repo": V2_SOURCE_REPO,
        "commit_sha": V2_COMMIT_SHA,
        "path": V2_PATH,
        "robot_version": "2.0",
        "identified_on": V2_IDENTIFIED_ON,
    }
    data.update(overrides)
    return Provenance(**data)


@pytest.fixture
def seed() -> SeedProfile:
    """The shipped read-only v1 seed profile."""
    return SeedProfileStore.default().load()


@pytest.fixture
def store() -> SeedProfileStore:
    """The default read-only seed store."""
    return SeedProfileStore.default()


@pytest.fixture
def converter() -> JointFrameConverter:
    """WP-2B-01's default v1->v2 converter: joint2 +pi/2 shift, no axis flips."""
    return JointFrameConverter.v2_default()


@pytest.fixture
def target_provenance() -> Provenance:
    """A valid v2 stamp for a promotion target."""
    return make_v2_provenance()
