"""The deferred live-registration acceptance (phase 2) — skipped with a reason, re-run by hook.

Live payload-registration verification needs the powered brakeless arm held torque-ON with a
real payload mounted, and cannot run on this host: no CAN, no motor, no PG-SAFE-001 PASS. It
is deferred — never asserted green. What is tested here is the re-verification hook: given a
real static-hold capture it registers the declared payload and re-runs the identical residual
check, confirming the registration only when the measured hold matches, and it refuses a
capture whose measurement disagrees with the declared payload, so the hook cannot manufacture
the registration pass THE ONE RULE forbids.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.gravity import Arm
from backend.payload import (
    Payload,
    PayloadGravityModel,
    fixture_dir_from_env,
    reverify_from_fixture,
    static_hold_torque,
)

_POSE = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)


def _capture(payload_declared: Payload, measured_tau: tuple[float, ...]) -> dict[str, object]:
    return {
        "arm": "right",
        "pose_rad": list(_POSE),
        "measured_tau_nm": list(measured_tau),
        "payload": {
            "mass_kg": payload_declared.mass_kg,
            "cog_m": list(payload_declared.cog_m),
            "label": payload_declared.label,
        },
    }


def _write(directory: Path, name: str, body: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(body), encoding="utf-8")


def test_live_registration_deferred_without_real_fixture() -> None:
    # Phase 2: with no fixture directory the live registration verify is deferred, not asserted.
    if fixture_dir_from_env() is not None:
        pytest.skip("real fixture present; the deferred path is not exercised")
    pytest.skip(
        "live payload registration verification requires the powered arm held torque-ON with "
        "a mounted payload; deferred to the real fixture via OPENARM_PAYLOAD_REAL_FIXTURE — "
        "never asserted green here (WP-2B-04 phase 2)"
    )


def test_hook_confirms_matching_capture(tmp_path: Path) -> None:
    # A capture whose measured hold matches the declared payload is confirmed.
    payload = Payload.from_cog(3.0, (0.01, -0.02, -0.05), "held-tool")
    model = PayloadGravityModel(Arm.RIGHT)
    measured = static_hold_torque(model, _POSE, payload)
    _write(tmp_path, "right.json", _capture(payload, measured))

    results = reverify_from_fixture(tmp_path)
    assert len(results) == 1
    assert results[0].confirmed
    assert not results[0].check.misdetected
    assert results[0].payload_label == "held-tool"


def test_hook_refuses_mismatched_capture(tmp_path: Path) -> None:
    # A capture whose measured hold is a 5 kg payload but declares 1 kg is NOT confirmed.
    model = PayloadGravityModel(Arm.RIGHT)
    physical = Payload.at_mount(5.0, "physical")
    declared = Payload.at_mount(1.0, "declared")
    measured = static_hold_torque(model, _POSE, physical)
    _write(tmp_path, "mismatch.json", _capture(declared, measured))

    verification = reverify_from_fixture(tmp_path)[0]
    assert not verification.confirmed
    assert verification.check.misdetected


def test_hook_raises_on_empty_fixture_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no .* static-hold capture"):
        reverify_from_fixture(tmp_path)
