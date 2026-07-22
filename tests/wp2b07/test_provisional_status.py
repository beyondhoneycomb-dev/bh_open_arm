"""THE ONE RULE: a synthetic-log fit is written provisional and can never claim a PG-FRIC-001 pass.

A synthetic-log fit proves the identification math; it is not a hardware pass. The written file
must say so — a deferred gate status, a synthetic basis, a re-verification hook — and there must
be no code path that turns it green. This is the rule that a synthetic fit is never presented as
a real PG-FRIC-001 pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.dynamics.provenance import Provenance
from backend.friction import (
    IdentificationResult,
    SyntheticLog,
    write_identified_friction,
)
from backend.friction.constants import (
    BASIS_SYNTHETIC_LOG,
    FIXTURE_ENV_VAR,
    PG_FRIC_001_STATUS_DEFERRED,
)

_PROVENANCE = Provenance(
    source_repo="bh_open_arm",
    commit_sha="SYNTHETIC-NO-HARDWARE",
    path="backend/friction/friction.provisional.yaml",
    robot_version="2.0",
    identified_on="2026-07-22",
)


def test_status_is_deferred_not_passed(document: dict[str, Any]) -> None:
    status = document["status"]
    assert status["pg_fric_001"] == PG_FRIC_001_STATUS_DEFERRED
    assert status["provisional"] is True
    assert status["basis"] == BASIS_SYNTHETIC_LOG


def test_status_never_reads_as_a_pass(document: dict[str, Any]) -> None:
    # No code path sets the gate to passed; the value must not be a pass-like token.
    assert "PASS" not in document["status"]["pg_fric_001"].upper().replace("NOT_PASSED", "")


def test_status_ships_the_reverify_hook(document: dict[str, Any]) -> None:
    hook = document["status"]["reverify_hook"]
    assert hook["module"] == "backend.friction.reverify"
    assert hook["env_var"] == FIXTURE_ENV_VAR
    assert document["status"]["real_pass_requires"]


def test_provenance_is_complete(document: dict[str, Any]) -> None:
    provenance = document["provenance"]
    for field_name in ("source_repo", "commit_sha", "path", "robot_version", "identified_on"):
        assert provenance[field_name]


def test_written_file_round_trips_provisional(
    tmp_path: Path, result: IdentificationResult, synthetic: SyntheticLog
) -> None:
    path = tmp_path / "friction.provisional.yaml"
    write_identified_friction(path, result, synthetic.log, _PROVENANCE)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["status"]["pg_fric_001"] == PG_FRIC_001_STATUS_DEFERRED
    assert loaded["status"]["provisional"] is True
    assert len(loaded["joints"]) == 7
