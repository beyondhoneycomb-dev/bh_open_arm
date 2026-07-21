"""The CLI exits zero on the true ledger and non-zero on a broken one."""

from __future__ import annotations

from pathlib import Path

from registry.normalization.cli import EXIT_OK, EXIT_VIOLATIONS, main
from registry.normalization.loader import LEDGER_PATH

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "registry" / "normalization" / "fixtures"


def test_cli_accepts_the_real_ledger() -> None:
    """`--check` over the shipped ledger exits zero."""
    assert main(["--check", "--root", str(REPO_ROOT), "--ledger", str(LEDGER_PATH)]) == EXIT_OK


def test_cli_rejects_a_schema_violation() -> None:
    """`--check` over a schema-invalid fixture exits non-zero."""
    ledger = FIXTURE_DIR / "empty_winners.yaml"
    assert main(["--check", "--root", str(REPO_ROOT), "--ledger", str(ledger)]) == EXIT_VIOLATIONS


def test_cli_rejects_a_semantic_violation() -> None:
    """`--check` over a corpus-dishonest fixture exits non-zero."""
    ledger = FIXTURE_DIR / "winner_undefined.yaml"
    assert main(["--check", "--root", str(REPO_ROOT), "--ledger", str(ledger)]) == EXIT_VIOLATIONS


def test_cli_emits_json(capsys) -> None:
    """`--json` emits a machine-readable report with a verdict."""
    main(["--check", "--json", "--root", str(REPO_ROOT), "--ledger", str(LEDGER_PATH)])
    captured = capsys.readouterr().out
    assert '"green": true' in captured
