"""Provenance-less safety parameters are unloadable (FR-SAF-067).

Every safety parameter must carry a complete
`{source_repo, commit_sha, path, robot_version, identified_on}` stamp. An asset with no
provenance, or a stamp with a blank or missing field, is refused at read time — the value is
never silently adopted.
"""

from __future__ import annotations

import pytest

from backend.dynamics.asset import load_safety_params
from backend.dynamics.constants import ARM_JOINT_COUNT, PROVENANCE_FIELDS
from backend.dynamics.errors import DynamicsConversionError
from backend.dynamics.provenance import Provenance
from tests.wp2b01.conftest import make_v1_provenance


def test_asset_without_provenance_is_unloadable() -> None:
    """An asset carrying safety params but no provenance is refused."""
    with pytest.raises(DynamicsConversionError, match="no provenance"):
        load_safety_params({"seed_pose_rad": [0.0] * ARM_JOINT_COUNT})


@pytest.mark.parametrize("missing", PROVENANCE_FIELDS)
def test_each_missing_provenance_field_is_refused(missing: str) -> None:
    """Dropping any one of the five required provenance fields refuses the load."""
    provenance = make_v1_provenance()
    del provenance[missing]
    with pytest.raises(DynamicsConversionError, match="missing required field"):
        load_safety_params({"provenance": provenance}, strict=False)


@pytest.mark.parametrize("blank", PROVENANCE_FIELDS)
def test_each_blank_provenance_field_is_refused(blank: str) -> None:
    """A blank (whitespace-only) value in any required field refuses the load."""
    with pytest.raises(DynamicsConversionError, match="must be a non-empty string"):
        Provenance(**make_v1_provenance(**{blank: "   "}))


def test_unknown_provenance_field_is_refused() -> None:
    """A stamp carrying a field outside the frozen five is refused, not silently ignored."""
    provenance = make_v1_provenance()
    provenance["author"] = "someone"
    with pytest.raises(DynamicsConversionError, match="unknown provenance field"):
        load_safety_params({"provenance": provenance}, strict=False)


def test_complete_provenance_round_trips() -> None:
    """A complete stamp builds and its `to_dict` returns exactly the five fields."""
    stamp = Provenance(**make_v1_provenance())
    assert set(stamp.to_dict()) == set(PROVENANCE_FIELDS)
    assert stamp.is_v2() is False
