"""Acceptance ②: the `k_eff = 0.1 * k` convention holds in the model and in the file metadata.

The runtime multiplies the stored `k` by 0.1 (spec 04 FR-MAN-034), so the parameter record and
the written file must both make the stored `k` a tenth of the tanh slope. A file that omitted
this would deploy a friction ten times too soft in the stiction knee.
"""

from __future__ import annotations

from typing import Any

from backend.friction import FrictionParams, IdentificationResult
from backend.friction.constants import K_EFF_SCALE


def test_stored_k_is_ten_times_k_eff() -> None:
    params = FrictionParams(f_o=0.05, f_v=0.4, f_c=1.2, k_eff=4.0)
    assert params.k == params.k_eff / K_EFF_SCALE
    assert params.k == 40.0


def test_from_stored_k_applies_the_scale() -> None:
    params = FrictionParams.from_stored_k(f_o=0.05, f_v=0.4, f_c=1.2, k=40.0)
    assert params.k_eff == K_EFF_SCALE * 40.0
    assert params.k_eff == 4.0


def test_metadata_states_the_convention(document: dict[str, Any]) -> None:
    convention = document["k_convention"]
    assert convention["scale"] == K_EFF_SCALE
    assert convention["applied"] == "k_eff = 0.1 * k"
    assert "0.1" in convention["note"]


def test_every_joint_row_stores_k_as_ten_times_k_eff(
    document: dict[str, Any], result: IdentificationResult
) -> None:
    for row, fit in zip(document["joints"], result.fits, strict=True):
        # The written k must reconstruct the fitted slope under the runtime's 0.1 multiply.
        assert abs(K_EFF_SCALE * row["k"] - fit.params.k_eff) < 1.0e-5
        assert abs(row["k"] - 10.0 * row["k_eff"]) < 1.0e-4
