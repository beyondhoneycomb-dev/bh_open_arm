"""FAIL_BLOCKING — a v1 value silently loaded into the v2 runtime is asset contamination.

`02b` WP-2B-10's blocking failure: the v1 seed reaching the v2 runtime. `load_into_v2_runtime` is
the single gate, and it refuses anything not stamped robot_version "2.0" loudly, so the leak is
impossible to do silently.
"""

from __future__ import annotations

import pytest

from backend.dynamics.constants import ARM_JOINT_COUNT
from backend.dynamics.errors import DynamicsConversionError
from backend.seed_profile.errors import SeedContaminationError
from backend.seed_profile.profile import SeedProfile
from backend.seed_profile.runtime import load_into_v2_runtime
from tests.wp2b10.conftest import make_v2_provenance


def test_raw_seed_is_refused_by_the_v2_runtime(seed: SeedProfile) -> None:
    """Feeding the v1 seed straight into the v2 runtime is refused as contamination."""
    with pytest.raises(SeedContaminationError, match="contamination"):
        load_into_v2_runtime(seed.as_v1_mapping())


def test_contamination_refusal_is_loud_about_the_version(seed: SeedProfile) -> None:
    """The refusal names the offending v1 version and the FAIL_BLOCKING semantics — not silent."""
    with pytest.raises(SeedContaminationError) as excinfo:
        load_into_v2_runtime(seed.as_v1_mapping())
    message = str(excinfo.value)
    assert "1.0" in message
    assert "FAIL_BLOCKING" in message


def test_v2_asset_passes_the_runtime_gate() -> None:
    """A genuinely v2-stamped asset loads."""
    asset = {
        "provenance": make_v2_provenance().to_dict(),
        "seed_pose_rad": [0.0] * ARM_JOINT_COUNT,
    }
    loaded = load_into_v2_runtime(asset)
    assert loaded.provenance.is_v2()


def test_intermediate_version_is_refused() -> None:
    """A non-2.0 stamp that is neither the seed's 1.0 is still refused — only 2.0 is admitted."""
    asset = {
        "provenance": make_v2_provenance(robot_version="1.5").to_dict(),
        "seed_pose_rad": [0.0] * ARM_JOINT_COUNT,
    }
    with pytest.raises(SeedContaminationError):
        load_into_v2_runtime(asset)


def test_unstamped_asset_is_refused() -> None:
    """An asset with no provenance cannot enter the v2 runtime either (WP-2B-01 gate)."""
    with pytest.raises(DynamicsConversionError, match="no provenance"):
        load_into_v2_runtime({"seed_pose_rad": [0.0] * ARM_JOINT_COUNT})


def test_seed_exposes_no_v2_mapping(seed: SeedProfile) -> None:
    """The seed's only exported mapping is v1-stamped, so it can never pass the gate directly."""
    exported = seed.as_v1_mapping()
    assert exported["provenance"]["robot_version"] == "1.0"
    assert not hasattr(seed, "as_v2_mapping")
