"""Plan 02a §4.1 — the real-fixture re-verification hook.

Two tests, the honest shape of a deferral. `test_hook_reruns_over_a_real_format_capture`
proves the hook machinery is not a stub: it serialises the fixture descriptors to the
exact JSON a real capture would carry, points the hook at that directory, and checks
the re-derived matrix / bandwidth / slop / drop / binding all come back. Only the
hardware *bytes* are pending. `test_real_capture_reverify` skips with a reason until
`OPENARM_CAMERA_REAL_FIXTURE` names a real camera capture, at which point it re-runs the
identical computations against real output — no green is faked, none is dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.camera import fixtures
from backend.camera.descriptor import CameraDescriptor
from backend.camera.reverify import (
    fixture_dir_from_env,
    reverify_from_fixture,
)


def _descriptor_to_mapping(descriptor: CameraDescriptor) -> dict[str, object]:
    """Serialise a descriptor to the JSON shape a real capture writes."""
    return {
        "serial": descriptor.serial,
        "camera_type": descriptor.camera_type.value,
        "model": descriptor.model,
        "controller": descriptor.controller,
        "link_speed": descriptor.link_speed.value,
        "profiles": [
            {
                "width": p.width,
                "height": p.height,
                "fps": p.fps,
                "bpp": p.bpp,
                "stream_kind": p.stream_kind.value,
            }
            for p in descriptor.profiles
        ],
    }


def _write_capture(directory: Path) -> None:
    """Write a full real-format capture directory the hook can consume."""
    descriptors = [
        fixtures.realsense_rgbd(),
        fixtures.webcam_720p(),
        fixtures.usb2_fallback_webcam(),
    ]
    (directory / "descriptors.json").write_text(
        json.dumps([_descriptor_to_mapping(d) for d in descriptors]), encoding="utf-8"
    )
    (directory / "capture_ts.json").write_text(
        json.dumps(fixtures.capture_ts_pair(slop_ns=5_000_000, frame_count=50)), encoding="utf-8"
    )
    (directory / "frames.json").write_text(
        json.dumps(
            {
                "wrist": {"target_fps": 30, "duration_s": 10, "received": 297},
                "front": {
                    "target_fps": 30,
                    "duration_s": 9 / 30,
                    "received": 9,
                    "frame_numbers": fixtures.frame_numbers_with_drops(),
                },
            }
        ),
        encoding="utf-8",
    )
    (directory / "binding.json").write_text(
        json.dumps(fixtures.serial_based_binding_spec()), encoding="utf-8"
    )
    (directory / "expected.json").write_text(
        json.dumps({"effective_cap_mbps": 3200}), encoding="utf-8"
    )


def test_hook_reruns_over_a_real_format_capture(tmp_path: Path) -> None:
    """The hook re-derives every measure from a genuine capture directory, not a stub."""
    _write_capture(tmp_path)
    report = reverify_from_fixture(tmp_path)

    assert {row.serial for row in report.matrix} == {
        "rs-0001",
        "uvc-logitech-720",
        "uvc-fallback-480",
    }
    assert report.bandwidth.effective_cap_mbps == 3200
    assert report.bandwidth.blocked is False
    assert report.slop_reports and report.slop_reports[0].q50_ms == pytest.approx(5.0)
    assert report.drop_reports["wrist"].drop_fraction == pytest.approx(0.01)
    assert report.drop_reports["front"].missing_frame_numbers == (3, 7)
    assert report.binding_ok is True


def test_hook_rejects_an_index_bound_capture(tmp_path: Path) -> None:
    """A real capture whose binding is index-based is rejected by the same gate (⑧)."""
    _write_capture(tmp_path)
    (tmp_path / "binding.json").write_text(
        json.dumps(fixtures.index_based_binding_spec()), encoding="utf-8"
    )
    with pytest.raises(Exception, match="index"):
        reverify_from_fixture(tmp_path)


def test_missing_descriptors_file_is_an_error(tmp_path: Path) -> None:
    """The hook fails loudly when the required descriptors file is absent."""
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason="no real camera capture: set OPENARM_CAMERA_REAL_FIXTURE to a captured "
    "descriptors.json (+ optional capture_ts.json/frames.json/binding.json) directory",
)
def test_real_capture_reverify() -> None:
    """Re-run the harness against a real captured camera set when one is supplied.

    Deferred acceptance ①③⑥: real enumeration, real controller membership, real drop
    rate — verified the moment a rig capture exists, using the identical calculators.
    """
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    report = reverify_from_fixture(fixture_dir)
    assert report.matrix, "a real capture must enumerate at least one camera"
    for row in report.matrix:
        assert row.serial and not row.serial.isdigit(), "real binding must be serial-based"
