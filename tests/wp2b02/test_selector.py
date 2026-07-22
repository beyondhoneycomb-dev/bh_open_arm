"""WP-2B-02: the backend selector builds either backend for either arm (FR-SAF-034)."""

from __future__ import annotations

from backend.gravity import (
    Arm,
    BackendId,
    MuJoCoV2GravityBackend,
    UrdfKdlGravityBackend,
    select_backend,
)


def test_selector_builds_the_requested_backend() -> None:
    """Each `BackendId` maps to its concrete backend."""
    assert isinstance(select_backend(BackendId.MUJOCO_V2), MuJoCoV2GravityBackend)
    assert isinstance(select_backend(BackendId.URDF_KDL), UrdfKdlGravityBackend)


def test_selector_builds_either_arm() -> None:
    """Both arms are constructible under both backends, and the arm is carried through."""
    for backend_id in (BackendId.MUJOCO_V2, BackendId.URDF_KDL):
        for arm in (Arm.RIGHT, Arm.LEFT):
            backend = select_backend(backend_id, arm=arm)
            assert backend.arm is arm
            assert backend.backend_id is backend_id


def test_backend_id_matches_the_spec_enum_strings() -> None:
    """The selector values are the spec's `comp.dynamics_backend` strings (FR-SAF-034)."""
    assert BackendId.MUJOCO_V2.value == "MUJOCO_V2"
    assert BackendId.URDF_KDL.value == "URDF_KDL"
