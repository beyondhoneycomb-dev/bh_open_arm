"""CG-4A-04c (static) — zero code paths normalize with split-local statistics.

`02c` §1.4 ③ requires proving by STATIC check that no path builds a normalization
contract from a diagnostic (split-local) statistic — validation leakage must be
impossible, not merely discouraged. Two halves make this real:

  1. the owned product tree scans CLEAN (no diagnostic reaches the contract sink); and
  2. the scan BITES — a fixture that feeds a diagnostic into the sink is caught, so the
     clean result in (1) is a proof, not a checker that never fires (WP-BOOT-03).

The scan's non-vacuity rests on `pipeline` having a real `build_normalization_contract`
call whose argument is the TRAIN normalization, not a diagnostic; that call is present
and passes, so a clean tree is a meaningful clean.
"""

from __future__ import annotations

from pathlib import Path

from backend.training.normstats import scan_source, scan_tree

_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "backend" / "training" / "normstats"
_LEAKY_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "leaky_contract.py"


def test_owned_tree_has_no_diagnostic_to_contract_flow() -> None:
    """The normstats product tree feeds no split-local statistic into the contract."""
    assert scan_tree(_PACKAGE_DIR) == []


def test_owned_tree_has_a_real_contract_call_so_the_scan_is_not_vacuous() -> None:
    """A real `build_normalization_contract` call exists in the tree (pipeline)."""
    pipeline = _PACKAGE_DIR / "pipeline.py"
    source = pipeline.read_text(encoding="utf-8")
    assert "build_normalization_contract(" in source


def test_the_scan_bites_on_a_leaky_fixture() -> None:
    """A fixture feeding a diagnostic into the contract sink is caught on every form."""
    violations = scan_source(_LEAKY_FIXTURE, _LEAKY_FIXTURE.read_text(encoding="utf-8"))
    # Three leak forms: a producer call, a bound name, and a `.diagnostics` access.
    assert len(violations) == 3
    assert all(violation.symbol == "build_normalization_contract" for violation in violations)
