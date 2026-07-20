"""Command-line behaviour of `oa-contracts`.

Exit status is the contract with CI: a rule breach must be a non-zero exit and
a machine-readable row on stderr, because a checker whose findings only reach a
human's scrollback does not gate anything.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from registry.contracts.cli import EXIT_OK, EXIT_VIOLATION, main
from tests.boot05.conftest import MINI_REGISTRY, REPO_ROOT, schema_with

BASE = schema_with("robot_id", "joints")
BUMPED = schema_with("robot_id", "joints", "gripper_rad")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Build a scratch repository the CLI can be pointed at.

    Only the canonical plan document is copied: it is the one input the CLI
    must read from a real tree rather than a fabricated one.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path: Root of the scratch repository.
    """
    root = tmp_path / "repo"
    plan = root / "docs/plan"
    plan.mkdir(parents=True)
    name = "01-의존성-DAG-및-병렬화.md"
    shutil.copy(REPO_ROOT / "docs/plan" / name, plan / name)

    registry = root / "registry"
    registry.mkdir()
    (registry / "traceability.yaml").write_text(
        yaml.safe_dump(MINI_REGISTRY, allow_unicode=True), encoding="utf-8"
    )
    (registry / "contracts").mkdir()
    return root


def _schema_file(repo: Path, name: str, body: dict) -> str:
    """Write a contract schema and return its path.

    Args:
        repo: Scratch repository root.
        name: File name to write.
        body: Schema contents.

    Returns:
        str: Path to the written file.
    """
    path = repo / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


def _run(repo: Path, *args: str) -> int:
    """Invoke the CLI against a scratch repository.

    Args:
        repo: Scratch repository root.
        *args: Subcommand and its arguments.

    Returns:
        int: Process exit status.
    """
    return main(["--repo-root", str(repo), *args])


def test_build_writes_all_thirteen(repo: Path, capsys) -> None:
    """`build` registers the whole namespace (acceptance ①)."""
    assert _run(repo, "build") == EXIT_OK
    index = json.loads((repo / "registry/contracts/contract_index.json").read_text())
    assert len(index["contracts"]) == 13
    assert "13 generations" in capsys.readouterr().out


def test_verify_passes_on_a_clean_tree(repo: Path) -> None:
    """A generated index verifies (no over-blocking)."""
    _run(repo, "build")
    assert _run(repo, "verify") == EXIT_OK


def test_verify_fails_on_a_hand_edited_index(repo: Path, capsys) -> None:
    """`verify` is the static check that closes the bypass (acceptance ⑧)."""
    _run(repo, "build")
    path = repo / "registry/contracts/contract_index.json"
    index = json.loads(path.read_text())
    index["contracts"][0]["status"] = "FROZEN"
    path.write_text(json.dumps(index), encoding="utf-8")

    assert _run(repo, "verify") == EXIT_VIOLATION
    row = json.loads(capsys.readouterr().err.strip().splitlines()[0])
    assert set(row) >= {"rule_id", "severity", "location", "expected", "actual", "reason"}


def test_freeze_then_refreeze_with_optional_field_fails(repo: Path, capsys) -> None:
    """The optional-field fixture, through the shipped entry point."""
    base = _schema_file(repo, "v1.json", BASE)
    assert _run(repo, "freeze", "CTR-PLUG@v1", "--schema", base) == EXIT_OK
    capsys.readouterr()

    optional = _schema_file(repo, "v1b.json", BUMPED)
    assert _run(repo, "freeze", "CTR-PLUG@v1", "--schema", optional) == EXIT_VIOLATION
    assert json.loads(capsys.readouterr().err.strip())["rule_id"] == "CI-09"


def test_bump_succeeds_and_prints_triggers(repo: Path, capsys) -> None:
    """`freeze CTR-X@v2` is the bump, and it reports every consumer."""
    _run(repo, "freeze", "CTR-PLUG@v1", "--schema", _schema_file(repo, "v1.json", BASE))
    capsys.readouterr()

    bumped = _schema_file(repo, "v2.json", BUMPED)
    assert _run(repo, "freeze", "CTR-PLUG@v2", "--schema", bumped) == EXIT_OK
    out = capsys.readouterr().out
    assert "superseded CTR-PLUG@v1" in out
    for consumer in ("WP-0C-01", "WP-0C-05", "WP-1-02"):
        assert consumer in out


def test_semver_id_is_rejected_at_the_command_line(repo: Path, capsys) -> None:
    """Acceptance ⑤ through the entry point."""
    schema = _schema_file(repo, "s.json", BASE)
    assert _run(repo, "freeze", "CTR-ACT@1.2.0", "--schema", schema) == EXIT_VIOLATION
    assert json.loads(capsys.readouterr().err.strip())["rule_id"] == "CI-08"


def test_contract_outside_the_thirteen_is_rejected(repo: Path, capsys) -> None:
    """Acceptance ④ through the entry point."""
    schema = _schema_file(repo, "s.json", BASE)
    assert _run(repo, "freeze", "CTR-RTBUDGET@v1", "--schema", schema) == EXIT_VIOLATION
    assert json.loads(capsys.readouterr().err.strip())["rule_id"] == "CI-03c"


def test_check_start_blocks_then_allows(repo: Path) -> None:
    """Acceptance ⑨ through the entry point, both directions."""
    assert _run(repo, "check-start", "WP-0C-01") == EXIT_VIOLATION
    _run(repo, "freeze", "CTR-PLUG@v1", "--schema", _schema_file(repo, "v1.json", BASE))
    assert _run(repo, "check-start", "WP-0C-01") == EXIT_OK


def test_show_does_not_write(repo: Path) -> None:
    """`show` is a read-only projection."""
    assert _run(repo, "show") == EXIT_OK
    assert not (repo / "registry/contracts/contract_index.json").exists()
