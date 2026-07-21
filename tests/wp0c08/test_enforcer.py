"""The block is a BLOCK, not a warning (`10` FR-TRN-064 is `[확정]` M).

`enforce` must raise on a blocked cell so a caller cannot read the verdict and
proceed. This suite proves a blocked cell raises `PolicyCompatBlockedError` carrying the
reason, and that an allowed cell passes through untouched.
"""

from __future__ import annotations

import pytest

from backend.policy_matrix import (
    DatasetObsConfig,
    DeployRequest,
    PolicyCompatBlockedError,
    build_matrix,
    enforce,
    first_block,
)

_DEPLOY = DeployRequest(target_id="rtx_5090", mode="async")
_BIMANUAL_48 = DatasetObsConfig(bimanual=True, use_velocity_and_torque=True)


@pytest.fixture(scope="module")
def matrix():  # type: ignore[no-untyped-def]
    """The calculator over the on-disk registry and target matrix."""
    return build_matrix()


def test_blocked_cell_raises(matrix) -> None:  # type: ignore[no-untyped-def]
    """A blocked cell is a hard stop — enforcement raises, never warns."""
    cell = matrix.evaluate(_BIMANUAL_48, "smolvla", _DEPLOY)
    assert not cell.allowed
    with pytest.raises(PolicyCompatBlockedError) as excinfo:
        enforce(cell)
    assert "state_dim 48 > max_state_dim 32" in str(excinfo.value)
    assert excinfo.value.cell is cell


def test_allowed_cell_passes_through(matrix) -> None:  # type: ignore[no-untyped-def]
    """An allowed cell is returned unchanged."""
    cell = matrix.evaluate(_BIMANUAL_48, "groot", _DEPLOY)
    assert enforce(cell) is cell
    assert first_block(cell) is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
