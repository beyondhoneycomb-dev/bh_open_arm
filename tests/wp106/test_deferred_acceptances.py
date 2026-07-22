"""The deferred hardware acceptances (⑨-a/⑨-b sweep) — skipped with a reason, re-run by hook.

The command-following sweep needs the powered arm under the bootstrap limiter and cannot run
on this host: no CAN adapter, no motor, no PG-SAFE-001 PASS. It is deferred — never asserted
green. What is tested here is the re-verification *hook*: given real single-joint sweep
captures it re-applies the identical publication gate and computes tracking from the measured
column, and it refuses a capture that dropped a constraint or commanded over the limiter, so
the hook can never manufacture the sweep pass THE ONE RULE forbids.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.safety_bringup import (
    bootstrap_limiter_rad_s,
    fixture_dir_from_env,
    reverify_from_fixture,
)


def _write_capture(directory: Path, name: str, payload: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def test_sweep_acceptance_deferred_without_real_fixture() -> None:
    # ⑨-a/⑨-b: with no fixture directory the real sweep is deferred, not asserted.
    if fixture_dir_from_env() is not None:
        pytest.skip("real fixture present; the deferred path is not exercised")
    pytest.skip(
        "PG-VEL-001 command-following sweep requires the powered arm under the bootstrap "
        "limiter (single joint, mechanically constrained); deferred to the real fixture via "
        "OPENARM_SAFETY_BRINGUP_REAL_FIXTURE — never asserted green here (02a §4.1)"
    )


def test_hook_reverifies_real_capture_and_computes_tracking(tmp_path: Path) -> None:
    # The hook re-runs the gate over real numbers and reports tracking from the measured column.
    joint = 2
    limiter = bootstrap_limiter_rad_s()[joint]
    _write_capture(
        tmp_path,
        "joint2.json",
        {
            "joint_index": joint,
            "single_joint": True,
            "mechanically_constrained": True,
            "samples": [
                {"commanded_rad_s": limiter * 0.5, "measured_rad_s": limiter * 0.5 - 0.01},
                {"commanded_rad_s": limiter * 0.9, "measured_rad_s": limiter * 0.9 - 0.02},
            ],
        },
    )
    results = reverify_from_fixture(tmp_path)
    assert len(results) == 1
    verification = results[0]
    assert verification.publication is not None
    assert verification.publication.commands_over_limiter == 0
    assert len(verification.publication.tracking_error_rad_s) == 2
    assert verification.publication.tracking_error_rad_s[0] == pytest.approx(0.01, abs=1e-6)


def test_hook_refuses_capture_over_limiter(tmp_path: Path) -> None:
    # A capture whose command exceeds the limiter is refused — the hook cannot self-approve.
    joint = 2
    limiter = bootstrap_limiter_rad_s()[joint]
    _write_capture(
        tmp_path,
        "over.json",
        {
            "joint_index": joint,
            "single_joint": True,
            "mechanically_constrained": True,
            "samples": [{"commanded_rad_s": limiter * 1.1, "measured_rad_s": limiter}],
        },
    )
    verification = reverify_from_fixture(tmp_path)[0]
    assert verification.publication is None
    assert "exceed the bootstrap limiter" in verification.refusal


def test_hook_refuses_multi_joint_capture(tmp_path: Path) -> None:
    _write_capture(
        tmp_path,
        "multi.json",
        {
            "joint_index": 0,
            "single_joint": False,
            "mechanically_constrained": True,
            "samples": [{"commanded_rad_s": 0.1, "measured_rad_s": 0.1}],
        },
    )
    verification = reverify_from_fixture(tmp_path)[0]
    assert verification.publication is None
    assert "single-joint" in verification.refusal


def test_hook_raises_on_empty_fixture_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no .* sweep capture"):
        reverify_from_fixture(tmp_path)
