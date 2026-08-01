"""The live-registration acceptance — deferred offline, run against a real static-hold capture.

Live payload-registration verification needs the powered brakeless arm held torque-ON with a
real payload mounted, which a desktop has none of, so offline it is skipped with a reason and
never asserted green. It stops being deferred the moment `PAYLOAD_FIXTURE_ENV_VAR` names a
capture directory: the acceptance then registers each declared payload and re-runs the
residual check over the measured hold, and a capture whose measurement disagrees with its
declared payload fails. The synthetic tests exercise both directions of that same check.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.gravity import Arm
from backend.payload import (
    PAYLOAD_FIXTURE_ENV_VAR,
    Payload,
    PayloadGravityModel,
    fixture_dir_from_env,
    reverify_from_fixture,
    static_hold_torque,
)

_POSE = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)

# Read once, at collection: the operator names the directory on the pytest command line, so
# the skip decision and the assertion below must see the same value. The skip turns on the raw
# string rather than the resolved directory — a mistyped path is a typo to report, not a
# deferral to honour, and resolving first would silently turn it back into a skip.
_FIXTURE_ENV_RAW = os.environ.get(PAYLOAD_FIXTURE_ENV_VAR, "")

_DEFERRED_REASON = (
    "live payload registration needs the powered arm held torque-ON with a mounted payload; "
    f"set {PAYLOAD_FIXTURE_ENV_VAR} to a directory of static-hold captures to run the "
    "acceptance here (WP-2B-04 phase 2)"
)


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


@pytest.mark.skipif(not _FIXTURE_ENV_RAW, reason=_DEFERRED_REASON)
def test_live_registration_against_the_real_fixture() -> None:
    # The deferred acceptance itself, over the operator's captures: every declared payload
    # must be confirmed by its own measured hold.
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None, (
        f"{PAYLOAD_FIXTURE_ENV_VAR} names {_FIXTURE_ENV_RAW!r}, which is not a directory"
    )
    verifications = reverify_from_fixture(fixture_dir)
    assert verifications, f"no static-hold capture in {fixture_dir}"
    for verification in verifications:
        assert verification.confirmed, (
            f"payload {verification.payload_label!r} was not confirmed: the measured static "
            "hold disagrees with the declared mass"
        )
        assert not verification.check.misdetected


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
