"""Acceptance (2) — a `robot_version != "2.0"` asset is load-blocked in strict mode.

`follower.yaml` predates the first v2.0 asset by ten months and reads no differently from a v2
value, so the strict gate — not human attention — is what keeps a v1-generation parameter out
of the v2 runtime (FR-SAF-067). In strict mode the load is refused; in non-strict mode it loads
with a warning so a deliberate inspection is still possible.
"""

from __future__ import annotations

import pytest

from backend.dynamics.asset import load_safety_params
from backend.dynamics.constants import ROBOT_VERSION_V2
from backend.dynamics.errors import DynamicsConversionError
from tests.wp2b01.conftest import make_v1_provenance


def test_v1_version_is_blocked_in_strict_mode() -> None:
    """A robot_version "1.0" asset is refused when strict mode is on (the runtime default)."""
    with pytest.raises(DynamicsConversionError, match="strict mode blocks load"):
        load_safety_params({"provenance": make_v1_provenance()}, strict=True)


def test_strict_is_the_default() -> None:
    """Omitting `strict` refuses a v1 asset — the v2 runtime never defaults to permissive."""
    with pytest.raises(DynamicsConversionError):
        load_safety_params({"provenance": make_v1_provenance()})


def test_arbitrary_non_v2_version_is_blocked() -> None:
    """Any version other than "2.0" is blocked, not only the known "1.0" tag."""
    with pytest.raises(DynamicsConversionError, match="strict mode blocks load"):
        load_safety_params({"provenance": make_v1_provenance(robot_version="1.5")}, strict=True)


def test_v1_version_loads_with_warning_in_non_strict_mode() -> None:
    """Non-strict mode loads a v1 asset but records the contamination warning."""
    loaded = load_safety_params({"provenance": make_v1_provenance()}, strict=False)
    assert loaded.provenance.robot_version == "1.0"
    assert len(loaded.warnings) == 1
    assert "not '2.0'" in loaded.warnings[0]


def test_v2_version_loads_clean_in_strict_mode() -> None:
    """A robot_version "2.0" asset passes the strict gate with no warnings."""
    loaded = load_safety_params(
        {"provenance": make_v1_provenance(robot_version=ROBOT_VERSION_V2)}, strict=True
    )
    assert loaded.provenance.robot_version == ROBOT_VERSION_V2
    assert loaded.warnings == ()
