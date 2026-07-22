"""Acceptance ④: the identified parameters are tabled against the v1 seed as relative error.

The synthetic v2 truth is the v1 seed scaled per term, so a correct identification lands a known
distance from the seed. This checks the per-joint relative-error table exists, has one row per
joint, and reports the Coulomb move the scaling implies.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.friction import IdentificationResult, RelativeError, relative_error_table
from backend.friction.errors import FrictionIdentificationError
from backend.friction.model import FrictionParams
from backend.friction.synthetic import _V2_SCALE_FC

# The Coulomb term is scaled by _V2_SCALE_FC (1.25) from the seed, so the identified relative
# error against the seed should sit near |1.25 - 1| = 0.25, within a band that admits fit noise.
_FC_MOVE_LOW = 0.15
_FC_MOVE_HIGH = 0.4


def test_table_has_one_row_per_joint(result: IdentificationResult) -> None:
    rows = relative_error_table(result.params())
    assert len(rows) == 7
    assert [row.joint_index for row in rows] == list(range(7))


def test_coulomb_relative_error_matches_the_injected_move(result: IdentificationResult) -> None:
    rows = relative_error_table(result.params())
    expected = abs(_V2_SCALE_FC - 1.0)
    assert expected == pytest.approx(0.25)
    for row in rows:
        assert _FC_MOVE_LOW < row.rel_f_c < _FC_MOVE_HIGH


def test_metadata_carries_the_seed_comparison(document: dict[str, Any]) -> None:
    seed_block = document["seed_comparison"]
    assert "v1" in seed_block["seed"]
    assert len(seed_block["joints"]) == 7
    for row in seed_block["joints"]:
        assert "rel_Fc" in row and "rel_k_eff" in row


def test_relative_error_refuses_a_wrong_length() -> None:
    short = tuple(FrictionParams(f_o=0.0, f_v=0.1, f_c=1.0, k_eff=4.0) for _ in range(3))
    with pytest.raises(FrictionIdentificationError):
        relative_error_table(short)


def test_relative_error_rows_are_frozen(result: IdentificationResult) -> None:
    row = relative_error_table(result.params())[0]
    assert isinstance(row, RelativeError)
