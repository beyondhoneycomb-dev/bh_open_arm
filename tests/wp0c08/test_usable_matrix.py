"""Acceptance ⑥ — 24→48 auto-removes the 32-capped policies, zero manual update.

`10` FR-TRN-065: the "usable policy matrix" recomputes from the observation config
and the introspected ceiling. Flipping a single dataset config field from the
24-dim to the 48-dim layout drops SmolVLA/pi0/pi05 from the usable set with no edit
to `contracts/policy_compat.yaml` or any table — the same loaded calculator is
reused across both queries to prove nothing was touched between them.
"""

from __future__ import annotations

import pytest

from backend.policy_matrix import DatasetObsConfig, DeployRequest, build_matrix

_DEPLOY = DeployRequest(target_id="rtx_5090", mode="async")
_UNIMANUAL_24 = DatasetObsConfig(bimanual=False, use_velocity_and_torque=True)
_BIMANUAL_48 = DatasetObsConfig(bimanual=True, use_velocity_and_torque=True)


def test_transition_drops_the_capped_policies_with_no_edit() -> None:
    """The 24→48 flip removes exactly SmolVLA/pi0/pi05; GR00T stays."""
    matrix = build_matrix()

    usable_24 = set(matrix.usable_policies(_UNIMANUAL_24, _DEPLOY))
    usable_48 = set(matrix.usable_policies(_BIMANUAL_48, _DEPLOY))

    assert {"smolvla", "pi0", "pi05", "groot"} <= usable_24
    assert usable_24 - usable_48 == {"smolvla", "pi0", "pi05"}
    assert "groot" in usable_48


def test_usable_set_is_a_pure_function_of_the_query() -> None:
    """Re-querying the untouched calculator yields the same sets — no hidden state."""
    matrix = build_matrix()
    assert matrix.usable_policies(_BIMANUAL_48, _DEPLOY) == matrix.usable_policies(
        _BIMANUAL_48, _DEPLOY
    )
    assert matrix.usable_policies(_UNIMANUAL_24, _DEPLOY) == matrix.usable_policies(
        _UNIMANUAL_24, _DEPLOY
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
