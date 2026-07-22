"""WP-2B-08 acceptance CG-2B-08a: the gravity+Coriolis compute is the v2-inertia `qfrc_bias`.

Path B loads the committed v2 MJCF and reads gravity+Coriolis from its bias force (spec 12 §2.6
path B). These tests pin three facts that together mean "v2-inertia-based, gravity+Coriolis only":
the source model is the committed v2 asset; the shoulder gravity term is the large non-zero value
a real v2 inertia model produces; and the bias carries a Coriolis term but no velocity-independent
friction offset (MJCF `frictionloss` is excluded by `qfrc_bias`, which is why friction stays
uncompensated and detection stays locked).
"""

from __future__ import annotations

from backend.gravity import MJCF_V2_PATH, Arm, MuJoCoV2GravityBackend
from backend.pathb import PathBBootstrap

# Shoulder gravity torque at the extended pose is many Nm; a zeroed/stub inertia model would give
# ~0. The floor only needs to be well clear of numerical noise to prove a real inertia model.
_SHOULDER_GRAVITY_FLOOR_NM = 1.0

# The bias reused from WP-2B-02 is deterministic for a fixed pose, so path B must reproduce it
# exactly, not within a physical tolerance.
_EXACT = 0.0


def test_source_model_is_the_committed_v2_mjcf() -> None:
    """The inertia source is `sim/mjcf/v2/openarm_bimanual.xml`, the committed v2 asset."""
    assert "v2" in MJCF_V2_PATH.parts
    assert MJCF_V2_PATH.name == "openarm_bimanual.xml"


def test_gravity_is_the_large_nonzero_v2_shoulder_term(
    bootstrap: PathBBootstrap, extended_pose: tuple[float, ...]
) -> None:
    """At the extended pose the shoulder gravity torque is large — a real v2 inertia model."""
    gravity = bootstrap.gravity(extended_pose)
    assert len(gravity) == 7
    assert abs(gravity[1]) > _SHOULDER_GRAVITY_FLOOR_NM


def test_bias_matches_the_wp2b02_v2_backend(
    bootstrap: PathBBootstrap,
    extended_pose: tuple[float, ...],
    moving_velocity: tuple[float, ...],
) -> None:
    """Path B's gravity+Coriolis is the reused WP-2B-02 v2 `qfrc_bias` single compute point."""
    expected = MuJoCoV2GravityBackend(Arm.RIGHT).tau_bias(extended_pose, moving_velocity)
    assert bootstrap.gravity_coriolis(extended_pose, moving_velocity) == expected


def test_zero_velocity_bias_carries_no_friction_offset(
    bootstrap: PathBBootstrap,
    extended_pose: tuple[float, ...],
    zero_velocity: tuple[float, ...],
) -> None:
    """At zero velocity the bias equals pure gravity: no velocity-independent friction term."""
    bias = bootstrap.gravity_coriolis(extended_pose, zero_velocity)
    gravity = bootstrap.gravity(extended_pose)
    for index in range(7):
        assert abs(bias[index] - gravity[index]) == _EXACT


def test_coriolis_term_is_present_when_moving(
    bootstrap: PathBBootstrap,
    extended_pose: tuple[float, ...],
    moving_velocity: tuple[float, ...],
) -> None:
    """A moving arm's bias differs from gravity alone — the Coriolis contribution is real."""
    moving = bootstrap.gravity_coriolis(extended_pose, moving_velocity)
    gravity = bootstrap.gravity(extended_pose)
    assert any(abs(moving[index] - gravity[index]) > _EXACT for index in range(7))


def test_both_arms_compute(extended_pose: tuple[float, ...]) -> None:
    """Both follower arms load and produce a seven-joint gravity vector."""
    for arm in (Arm.RIGHT, Arm.LEFT):
        gravity = PathBBootstrap(arm).gravity(extended_pose)
        assert len(gravity) == 7
