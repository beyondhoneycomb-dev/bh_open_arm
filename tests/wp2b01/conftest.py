"""Shared builders for the WP-2B-01 acceptance tests.

The canonical numbers are the spec's: the v1 seed carries the `follower.yaml` provenance
(source repo `openarm_teleop`, robot_version "1.0", the 2025-07-23 import commit), and the v2
target carries a robot_version "2.0" stamp dated at the conversion. `make_v1_asset` defaults to
a convertible asset (only convertible links) so a test opts into an unconvertible item by
passing one in.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.dynamics.constants import ARM_JOINT_COUNT
from backend.dynamics.converter import JointFrameConverter
from backend.dynamics.provenance import Provenance

V1_SOURCE_REPO = "openarm_teleop"
V1_COMMIT_SHA = "0000000000000000000000000000000000000001"
V1_PATH = "config/follower.yaml"
V1_IDENTIFIED_ON = "2025-07-23"

V2_SOURCE_REPO = "bh_open_arm"
V2_COMMIT_SHA = "0000000000000000000000000000000000000002"
V2_PATH = "backend/dynamics/converted/follower_v2.yaml"
V2_IDENTIFIED_ON = "2026-07-22"


def make_v1_provenance(**overrides: str) -> dict[str, str]:
    """Return the v1 seed provenance mapping, with any field overridden by keyword."""
    data = {
        "source_repo": V1_SOURCE_REPO,
        "commit_sha": V1_COMMIT_SHA,
        "path": V1_PATH,
        "robot_version": "1.0",
        "identified_on": V1_IDENTIFIED_ON,
    }
    data.update(overrides)
    return data


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


def make_v1_asset(**extra: Any) -> dict[str, Any]:
    """Build a convertible v1 seed asset, merging any extra keys.

    Defaults to only convertible inertial links (`link3`) and a zero seed pose, so a test
    introduces an unconvertible item by passing `inertials=` or `gripper_model=`.
    """
    asset: dict[str, Any] = {
        "provenance": make_v1_provenance(),
        "seed_pose_rad": [0.0] * ARM_JOINT_COUNT,
        "inertials": {"link3": {"mass": 1.07386}},
    }
    asset.update(extra)
    return asset


@pytest.fixture
def default_converter() -> JointFrameConverter:
    """The default v1->v2 converter WP-2B-02 consumes: joint2 +pi/2 shift, no axis flips."""
    return JointFrameConverter.v2_default()
