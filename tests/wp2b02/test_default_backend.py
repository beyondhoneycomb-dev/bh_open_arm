"""WP-2B-02 acceptance ②: the default backend is `MUJOCO_V2`, which uses v2 inertia.

FR-SAF-034 fixes the default because `MUJOCO_V2` computes gravity from v2 inertia via
`qfrc_bias`; `URDF_KDL` is the opt-in legacy path.
"""

from __future__ import annotations

from backend.gravity import Arm, BackendId, MuJoCoV2GravityBackend, select_backend


def test_selector_default_is_mujoco_v2() -> None:
    """`select_backend()` with no backend argument returns the v2-inertia backend."""
    backend = select_backend()
    assert backend.backend_id is BackendId.MUJOCO_V2
    assert isinstance(backend, MuJoCoV2GravityBackend)


def test_default_arm_is_the_reference_right_arm() -> None:
    """The default arm is the right arm — the arm WP-2B-01 froze the v2 convention against."""
    assert select_backend().arm is Arm.RIGHT


def test_default_gravity_scale_is_one() -> None:
    """The default gravity trim is 1.0 = full modelled gravity."""
    assert select_backend().gravity_scale == 1.0


def test_v2_inertia_produces_nonzero_shoulder_gravity(zero_pose: tuple[float, ...]) -> None:
    """A real v2-inertia model holds mass, so gravity at the extended shoulder is non-zero."""
    backend = select_backend()
    gravity = backend.tau_grav(zero_pose)
    # joint1 and joint2 carry the arm's weight at the zero pose; both must be non-trivial.
    assert abs(gravity[0]) > 1.0e-3
    assert abs(gravity[1]) > 1.0e-3
