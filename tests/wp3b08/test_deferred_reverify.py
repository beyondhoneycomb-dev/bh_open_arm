"""The deferred item: the LIVE WebXR session (real headset browser). SKIP + hook proof.

Everything WP-3B-08 fixes runs here on synthetic controllers (profile resolution, the
buttons[1] squeeze read, the axes-count joystick guard, single-arm admission). What
cannot run here is a REAL `immersive-ar` session: WebXR requires a headset browser and
the Quest 3S's reported profile strings are unconfirmed (`05` §5 U-6), and this host is
a dev desktop with no headset. That acceptance is SKIPPED WITH A REASON, never asserted
green, and wired to `backend.teleop.webxr.reverify`, which re-runs the exact resolver,
gamepad reads and session admission against a real captured session named by
`OPENARM_WEBXR_REAL_FIXTURE` (plan 02a §4.1).

To prove the hook is real and not a stub, the hook-proof tests build a `session.json`
in the schema the hook loads and run `reverify_from_fixture` end to end. That exercises
the plumbing without pretending to reach a headset; the hardware truth stays in the
skipped test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.teleop.webxr.profiles import ResolvedVia
from backend.teleop.webxr.reverify import (
    FIXTURE_ENV_VAR,
    SESSION_FILENAME,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.teleop.webxr.session import Handedness, TeleopMode

_REAL_FIXTURE = fixture_dir_from_env()

# One controller in the schema the hook loads: an unknown profile plus an xr-standard
# gamepad, which is exactly the case a real Quest 3S is expected to present.
_SOURCE_RECORD = {
    "handedness": "right",
    "profiles": ["meta-quest-3s-unconfirmed"],
    "mapping": "xr-standard",
    "buttons": [0.0, 0.66, 0.0, 0.0, 0.0, 0.0],
    "axes": [0.0, 0.0, 0.3, -0.4],
}


def _write_session(directory: Path, spec: dict[str, object]) -> None:
    """Write one session.json into a directory in the schema the hook loads."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SESSION_FILENAME).write_text(json.dumps(spec), encoding="utf-8")


@pytest.mark.skipif(
    _REAL_FIXTURE is None,
    reason=(
        f"live WebXR session needs a headset browser and a real Quest 3S; set "
        f"{FIXTURE_ENV_VAR} to a captured session directory to re-run the deferred "
        "acceptance against real reported profiles"
    ),
)
def test_live_webxr_session_against_real_capture() -> None:
    # Runs only when a real captured session is supplied. The fallback chain must admit
    # the real headset's reported profile and its gamepad must parse.
    assert _REAL_FIXTURE is not None
    report = reverify_from_fixture(_REAL_FIXTURE)
    assert report.arms
    for arm in report.arms:
        assert arm.resolved_via in (ResolvedVia.CHAIN, ResolvedVia.XR_STANDARD)


def test_hook_admits_unknown_profile_via_xr_standard(tmp_path: Path) -> None:
    _write_session(tmp_path, {"mode": "right", "input_sources": [_SOURCE_RECORD]})
    report = reverify_from_fixture(tmp_path)
    assert report.mode is TeleopMode.RIGHT
    assert len(report.arms) == 1
    arm = report.arms[0]
    assert arm.handedness is Handedness.RIGHT
    assert arm.resolved_via is ResolvedVia.XR_STANDARD
    assert arm.squeeze == pytest.approx(0.66)
    assert arm.thumbstick_transmittable is True


def test_hook_reports_short_axis_array_as_not_transmittable(tmp_path: Path) -> None:
    record = dict(_SOURCE_RECORD, axes=[0.0, 0.0, 0.3])
    _write_session(tmp_path, {"mode": "right", "input_sources": [record]})
    report = reverify_from_fixture(tmp_path)
    assert report.arms[0].thumbstick_transmittable is False


def test_hook_admits_bimanual_capture(tmp_path: Path) -> None:
    left = dict(_SOURCE_RECORD, handedness="left")
    right = dict(_SOURCE_RECORD, handedness="right")
    _write_session(tmp_path, {"mode": "bimanual", "input_sources": [left, right]})
    report = reverify_from_fixture(tmp_path)
    assert {arm.handedness for arm in report.arms} == {Handedness.LEFT, Handedness.RIGHT}


def test_hook_raises_on_missing_session_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)
