"""Verify the tag types produce *type* errors, not runtime errors (WP-0A-04).

Acceptance items 1, 2, 3, 6 and 8 all state "타입 오류(런타임 아님)": the failure
must be caught statically by mypy. Each fixture under `fixtures/` is a file that
must fail mypy with a specific error code; a positive-control fixture must pass, so
the suite proves the types distinguish wrong from right rather than rejecting
everything.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"

# (fixture filename, mypy error code the acceptance item hinges on).
TYPE_ERROR_CASES = [
    ("mypy_01_assign_rad_to_deg.py", "assignment"),
    ("mypy_02_mixed_arithmetic.py", "operator"),
    ("mypy_03_implicit_reconstruction.py", "arg-type"),
    ("mypy_06_bare_float_quantity.py", "assignment"),
    ("mypy_08_torque_packet_scale.py", "arg-type"),
]

OK_FIXTURE = "mypy_ok_clean_usage.py"


def _run_mypy(fixture: str) -> subprocess.CompletedProcess[str]:
    """Run mypy --strict over one fixture from the repository root.

    Args:
        fixture: Fixture filename under `fixtures/`.

    Returns:
        (CompletedProcess) The finished mypy process, output captured.
    """
    environment = {**os.environ, "MYPYPATH": str(REPO_ROOT)}
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--namespace-packages",
            "--explicit-package-bases",
            "--no-incremental",
            "--show-error-codes",
            "--no-error-summary",
            str(FIXTURES / fixture),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(("fixture", "code"), TYPE_ERROR_CASES)
def test_fixture_is_a_type_error(fixture: str, code: str) -> None:
    """Each violation fixture fails mypy with its acceptance-specific code."""
    result = _run_mypy(fixture)
    assert result.returncode != 0, f"{fixture} was expected to fail mypy but passed"
    assert f"[{code}]" in result.stdout, (
        f"{fixture} failed mypy but not with [{code}]; got:\n{result.stdout}"
    )


def test_clean_usage_passes_mypy() -> None:
    """The positive control type-checks, proving the types are not just always red."""
    result = _run_mypy(OK_FIXTURE)
    assert result.returncode == 0, (
        f"{OK_FIXTURE} was expected to pass mypy but failed:\n{result.stdout}"
    )
