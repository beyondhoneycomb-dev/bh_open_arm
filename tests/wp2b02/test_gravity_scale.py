"""WP-2B-02 acceptance ③: `gravity_scale` is runtime-exposed, in `[0, 1.2]`, default 1.0.

The trim scales the gravity torque linearly and is validated on every set, so an out-of-band
payload trim is refused rather than silently adopted.
"""

from __future__ import annotations

import pytest

from backend.gravity import (
    GRAVITY_SCALE_MAX,
    GRAVITY_SCALE_MIN,
    BackendId,
    GravityBackendError,
    select_backend,
)


def test_scale_zero_zeroes_the_gravity_torque(pose_grid: tuple[tuple[float, ...], ...]) -> None:
    """A gravity_scale of 0 turns the gravity term off entirely."""
    backend = select_backend(gravity_scale=0.0)
    for pose in pose_grid:
        assert all(torque == 0.0 for torque in backend.tau_grav(pose))


def test_scale_is_a_linear_multiplier(pose_grid: tuple[tuple[float, ...], ...]) -> None:
    """`tau_grav` at scale s equals s times `tau_grav` at scale 1, per joint."""
    trimmed = select_backend(gravity_scale=0.75)
    full = select_backend(gravity_scale=1.0)
    for pose in pose_grid:
        scaled = trimmed.tau_grav(pose)
        base = full.tau_grav(pose)
        for index in range(7):
            assert scaled[index] == pytest.approx(0.75 * base[index], abs=1.0e-12)


def test_scale_is_settable_at_runtime(zero_pose: tuple[float, ...]) -> None:
    """Setting `gravity_scale` after construction changes subsequent results."""
    backend = select_backend()
    high = backend.tau_grav(zero_pose)
    backend.gravity_scale = 0.5
    assert backend.gravity_scale == 0.5
    low = backend.tau_grav(zero_pose)
    for index in range(7):
        assert low[index] == pytest.approx(0.5 * high[index], abs=1.0e-12)


def test_band_endpoints_are_accepted() -> None:
    """The band endpoints 0.0 and 1.2 are valid trims."""
    assert select_backend(gravity_scale=GRAVITY_SCALE_MIN).gravity_scale == GRAVITY_SCALE_MIN
    assert select_backend(gravity_scale=GRAVITY_SCALE_MAX).gravity_scale == GRAVITY_SCALE_MAX


@pytest.mark.parametrize("bad_scale", [-0.1, 1.2001, 2.0, -1.0])
def test_out_of_band_scale_is_refused(bad_scale: float) -> None:
    """A trim outside [0, 1.2] is refused both at construction and at runtime set."""
    with pytest.raises(GravityBackendError):
        select_backend(gravity_scale=bad_scale)
    backend = select_backend(BackendId.URDF_KDL)
    with pytest.raises(GravityBackendError):
        backend.gravity_scale = bad_scale
