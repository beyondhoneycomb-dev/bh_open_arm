"""The FR-MAN-047 adoption is recorded; the operator visual-confirm is never faked.

The AI-offline decision (home = J4=π/2, J4=0 hardstop rejected) is real and recorded. The
Human-judgment confirm — an operator looking at the arm and confirming the J4=0 pose is the
fully-extended hardstop — is SKIP-with-reason plus a hook that only ever echoes a real
operator observation and refuses a malformed one. It never fabricates a PASS.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from backend.home.constants import HARDSTOP_FIXTURE_ENV_VAR
from backend.home.decision import (
    CONFIRM_STATUS_SKIPPED,
    HOME_DECISION,
    deferred_visual_confirm,
    fixture_dir_from_env,
    reverify_visual_confirm,
)


def test_adoption_is_recorded() -> None:
    """③ The adopted decision is home = J4=π/2, with J4=0 recorded as the rejected hardstop."""
    assert HOME_DECISION.requirement == "FR-MAN-047"
    assert HOME_DECISION.adopted_j4_rad == pytest.approx(math.pi / 2)
    assert HOME_DECISION.rejected_j4_rad == 0.0
    assert HOME_DECISION.adopted_q_urdf == (
        0.0,
        0.0,
        0.0,
        HOME_DECISION.adopted_j4_rad,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    assert "FR-MAN-047" in HOME_DECISION.basis
    assert "FR-GUI-118" in HOME_DECISION.basis
    record = HOME_DECISION.as_record()
    assert record["adopted_home"] == "J4=pi/2"
    assert "hardstop" in record["rejected_home"]


def test_deferred_confirm_is_skip_with_reason_not_a_pass() -> None:
    """The operator visual-confirm is SKIPPED with a reason and a hook, never asserted PASS."""
    deferred = deferred_visual_confirm()
    assert deferred.status == CONFIRM_STATUS_SKIPPED
    assert deferred.status != "PASS"
    assert deferred.hook_env_var == HARDSTOP_FIXTURE_ENV_VAR
    assert "operator" in deferred.reason
    assert "offline" in deferred.reason


def test_reverify_echoes_a_real_operator_observation(tmp_path: Path) -> None:
    """The hook reports the operator's recorded verdict, not one it invented."""
    capture = {
        "operator": "op-7",
        "j4_zero_is_fully_extended_hardstop": True,
        "observed": "arm fully extended, J4 against the lower stop",
    }
    (tmp_path / "confirm.json").write_text(json.dumps(capture), encoding="utf-8")
    records = reverify_visual_confirm(tmp_path)
    assert len(records) == 1
    assert records[0].operator == "op-7"
    assert records[0].is_fully_extended_hardstop is True
    assert records[0].refusal == ""


def test_reverify_echoes_a_negative_verdict_without_flipping_it(tmp_path: Path) -> None:
    """A recorded 'not a hardstop' verdict is echoed as-is; the hook never manufactures a pass."""
    capture = {
        "operator": "op-7",
        "j4_zero_is_fully_extended_hardstop": False,
        "observed": "unclear",
    }
    (tmp_path / "confirm.json").write_text(json.dumps(capture), encoding="utf-8")
    (record,) = reverify_visual_confirm(tmp_path)
    assert record.is_fully_extended_hardstop is False


def test_reverify_refuses_a_capture_with_no_operator(tmp_path: Path) -> None:
    """A capture that names no operator is refused, with no fabricated verdict."""
    (tmp_path / "confirm.json").write_text(
        json.dumps({"j4_zero_is_fully_extended_hardstop": True}), encoding="utf-8"
    )
    (record,) = reverify_visual_confirm(tmp_path)
    assert record.is_fully_extended_hardstop is None
    assert "operator" in record.refusal


def test_reverify_refuses_a_non_boolean_verdict(tmp_path: Path) -> None:
    """A verdict that is not a boolean is refused rather than coerced to a pass."""
    (tmp_path / "confirm.json").write_text(
        json.dumps({"operator": "op-7", "j4_zero_is_fully_extended_hardstop": "yes"}),
        encoding="utf-8",
    )
    (record,) = reverify_visual_confirm(tmp_path)
    assert record.is_fully_extended_hardstop is None
    assert "boolean" in record.refusal


def test_reverify_with_no_captures_raises(tmp_path: Path) -> None:
    """An empty fixture directory is an error, not a silent green."""
    with pytest.raises(FileNotFoundError):
        reverify_visual_confirm(tmp_path)


def test_fixture_dir_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The hook directory comes from the environment, and is None when unset or absent."""
    monkeypatch.delenv(HARDSTOP_FIXTURE_ENV_VAR, raising=False)
    assert fixture_dir_from_env() is None
    monkeypatch.setenv(HARDSTOP_FIXTURE_ENV_VAR, str(tmp_path))
    assert fixture_dir_from_env() == tmp_path
    monkeypatch.setenv(HARDSTOP_FIXTURE_ENV_VAR, str(tmp_path / "missing"))
    assert fixture_dir_from_env() is None
