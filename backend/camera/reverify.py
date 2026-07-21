"""Real-fixture re-verification hook (plan 02a §4.1) for the camera harness.

Most of WP-0B-08 runs here on synthetic descriptors: the bandwidth formula, the
sync-slop distribution, the drop computer, and the index-binding rejection are all
pure functions over data. What does not run here is the same math over *real* captured
output — real enumerated descriptors, real capture_ts logs, real frame-number streams
— because there are no cameras on this host.

This hook is what the deferral is required to ship. The moment a directory of real
captures is supplied (via `OPENARM_CAMERA_REAL_FIXTURE`), `reverify_from_fixture`
re-runs the identical calculators against the real bytes and returns their verdicts.
Until then the bound test skips with a reason. The fixture directory holds:

- `descriptors.json`  — list of enumerated camera descriptors (required),
- `capture_ts.json`   — `{slot: [capture_ts_ns, ...]}` (optional),
- `frames.json`       — `{slot: {"target_fps", "duration_s", "received", "frame_numbers"?}}`,
- `binding.json`      — `{slot: serial}` to re-check serial-based binding (optional),
- `expected.json`     — `{"effective_cap_mbps": float}` cap for the bandwidth verdict.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.camera.bandwidth import BandwidthVerdict, evaluate_bandwidth
from backend.camera.binding import parse_binding_spec, resolve_bindings
from backend.camera.constants import USB3_EFFECTIVE_CAP_MBPS_REFERENCE
from backend.camera.descriptor import CameraDescriptor
from backend.camera.droprate import DropReport, compute_drop
from backend.camera.matrix import CapabilityRow, build_matrix
from backend.camera.syncslop import SyncSlopReport, build_slop_reports

FIXTURE_ENV_VAR = "OPENARM_CAMERA_REAL_FIXTURE"
DESCRIPTORS_FILENAME = "descriptors.json"
CAPTURE_TS_FILENAME = "capture_ts.json"
FRAMES_FILENAME = "frames.json"
BINDING_FILENAME = "binding.json"
EXPECTED_FILENAME = "expected.json"


@dataclass(frozen=True)
class ReverifyReport:
    """The result of re-running the harness over one real capture directory.

    Attributes:
        matrix: Capability matrix rebuilt from the real descriptors.
        bandwidth: Block verdict from the real profiles against the captured cap.
        slop_reports: Per-pair sync-slop reports, empty when no capture_ts was given.
        drop_reports: Per-slot drop reports, empty when no frames file was given.
        binding_ok: True when the captured binding was serial-based and resolvable;
            None when no binding file was supplied.
    """

    matrix: tuple[CapabilityRow, ...]
    bandwidth: BandwidthVerdict
    slop_reports: tuple[SyncSlopReport, ...]
    drop_reports: dict[str, DropReport]
    binding_ok: bool | None


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present."""
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_descriptors(path: Path) -> tuple[CameraDescriptor, ...]:
    """Load enumerated descriptors from a real capture's `descriptors.json`."""
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise TypeError(f"{path} must hold a list of descriptors")
    return tuple(CameraDescriptor.from_mapping(item) for item in raw)


def _reverify_binding(binding_path: Path, descriptors: tuple[CameraDescriptor, ...]) -> bool:
    """Re-run serial-based binding validation over a captured binding spec."""
    spec = _load_json(binding_path)
    if not isinstance(spec, Mapping):
        raise TypeError(f"{binding_path} must hold a slot→serial mapping")
    bindings = parse_binding_spec(spec)
    resolve_bindings(bindings, descriptors)
    return True


def reverify_from_fixture(fixture_dir: Path) -> ReverifyReport:
    """Re-run the camera harness against a directory of real captured output.

    Every computation is the one the synthetic tests exercise, pointed at real bytes —
    the point of the hook is that no path is re-implemented for hardware.

    Args:
        fixture_dir: Directory of captured JSON (see the module docstring).

    Returns:
        (ReverifyReport) The re-derived matrix, bandwidth verdict, slop and drop
        reports, and binding outcome.

    Raises:
        FileNotFoundError: If `descriptors.json` is missing.
    """
    descriptors_path = fixture_dir / DESCRIPTORS_FILENAME
    if not descriptors_path.is_file():
        raise FileNotFoundError(f"missing {DESCRIPTORS_FILENAME} in {fixture_dir}")
    descriptors = load_descriptors(descriptors_path)

    cap: float = USB3_EFFECTIVE_CAP_MBPS_REFERENCE
    expected_path = fixture_dir / EXPECTED_FILENAME
    if expected_path.is_file():
        cap = float(_load_json(expected_path).get("effective_cap_mbps", cap))

    slop_reports: tuple[SyncSlopReport, ...] = ()
    capture_ts_path = fixture_dir / CAPTURE_TS_FILENAME
    if capture_ts_path.is_file():
        streams = {
            slot: [int(t) for t in stamps] for slot, stamps in _load_json(capture_ts_path).items()
        }
        slop_reports = tuple(build_slop_reports(streams))

    drop_reports: dict[str, DropReport] = {}
    frames_path = fixture_dir / FRAMES_FILENAME
    if frames_path.is_file():
        for slot, spec in _load_json(frames_path).items():
            drop_reports[slot] = compute_drop(
                target_fps=float(spec["target_fps"]),
                duration_s=float(spec["duration_s"]),
                received_count=int(spec["received"]),
                frame_numbers=spec.get("frame_numbers"),
            )

    binding_ok: bool | None = None
    binding_path = fixture_dir / BINDING_FILENAME
    if binding_path.is_file():
        binding_ok = _reverify_binding(binding_path, descriptors)

    return ReverifyReport(
        matrix=build_matrix(descriptors),
        bandwidth=evaluate_bandwidth(descriptors, cap),
        slop_reports=slop_reports,
        drop_reports=drop_reports,
        binding_ok=binding_ok,
    )
