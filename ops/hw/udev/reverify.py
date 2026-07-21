"""Real-fixture re-verification hook for udev fixed names (plan 02a §4.1).

Most of this WP's acceptance is hardware-bound (`AI-on-HW`): the driver family, the
per-adapter serial sharing, the `dev_id` channel split, and the ten-reboot determinism
all need two physical adapters this host does not have. Those are not asserted green and
not dropped — they are deferred behind this hook.

The moment a directory of real captures is supplied (via `OPENARM_UDEV_REAL_FIXTURE` or an
explicit path), `reverify_from_fixture` re-runs the *identical* parsers and evaluators the
synthetic tests use, now pointed at real bytes, and checks each result against the recorded
expectation. The capture directory holds:

- `udevadm/<name>.txt`  — one `udevadm info -a -p /sys/class/net/<if>` dump per interface.
- `ethtool/<name>.txt`  — one `ethtool -i <if>` output per interface (optional).
- `reboots.json`        — `[{"reboot_index": int, "bindings": {name: key}}, ...]` (optional).
- `expected.json`       — recorded truth: `serial_shared`, `dev_id_distinguishes`, `all_in_tree`,
                          `determinism_stable` (each optional; only supplied keys are checked).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ops.hw.udev.determinism import (
    REQUIRED_REBOOT_CYCLES,
    RebootObservation,
    evaluate_determinism,
)
from ops.hw.udev.ethtool import is_in_tree_driver, parse_ethtool_i
from ops.hw.udev.measurement import (
    build_measurement_table,
    dev_id_distinguishes_channels,
    serial_shared_per_adapter,
)
from ops.hw.udev.parser import parse_udevadm_info

FIXTURE_ENV_VAR = "OPENARM_UDEV_REAL_FIXTURE"
EXPECTED_FILENAME = "expected.json"
UDEVADM_SUBDIR = "udevadm"
ETHTOOL_SUBDIR = "ethtool"
REBOOTS_FILENAME = "reboots.json"


@dataclass(frozen=True)
class ReverifyReport:
    """Outcome of re-running every runnable check against a real capture.

    Attributes:
        matched: True iff every expectation that was recorded held on the real bytes.
        checked: Names of the expectations that were present and evaluated.
        mismatches: One human-readable line per expectation that failed.
    """

    matched: bool
    checked: tuple[str, ...]
    mismatches: tuple[str, ...] = field(default_factory=tuple)


def fixture_dir_from_env() -> Path | None:
    """Return the real-capture directory named by the environment, if present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _load_reboots(path: Path) -> tuple[RebootObservation, ...]:
    """Load reboot observations from `reboots.json`.

    Args:
        path: Path to the reboot-capture JSON.

    Returns:
        (tuple[RebootObservation, ...]) One observation per recorded boot.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        RebootObservation(reboot_index=int(item["reboot_index"]), bindings=dict(item["bindings"]))
        for item in raw
    )


def reverify_from_fixture(fixture_dir: Path) -> ReverifyReport:
    """Re-run every runnable check against a directory of real captures.

    Only the expectations actually recorded in `expected.json` are evaluated, so a
    partial capture (say, udevadm dumps but no reboot log) verifies what it can and
    stays silent on the rest.

    Args:
        fixture_dir: Directory of real captures plus `expected.json`.

    Returns:
        (ReverifyReport) The aggregate verdict.

    Raises:
        FileNotFoundError: If `expected.json` is missing.
    """
    expected_path = fixture_dir / EXPECTED_FILENAME
    if not expected_path.is_file():
        raise FileNotFoundError(f"missing {EXPECTED_FILENAME} in {fixture_dir}")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    interfaces = tuple(
        parse_udevadm_info(dump.read_text(encoding="utf-8"))
        for dump in sorted((fixture_dir / UDEVADM_SUBDIR).glob("*.txt"))
    )
    table = build_measurement_table(interfaces)

    checked: list[str] = []
    mismatches: list[str] = []

    if "serial_shared" in expected:
        checked.append("serial_shared")
        got = serial_shared_per_adapter(table)
        if got != expected["serial_shared"]:
            mismatches.append(f"serial_shared: got {got}, expected {expected['serial_shared']}")

    if "dev_id_distinguishes" in expected:
        checked.append("dev_id_distinguishes")
        got = dev_id_distinguishes_channels(table)
        if got != expected["dev_id_distinguishes"]:
            mismatches.append(
                f"dev_id_distinguishes: got {got}, expected {expected['dev_id_distinguishes']}"
            )

    if "all_in_tree" in expected:
        checked.append("all_in_tree")
        reports = [
            parse_ethtool_i(dump.read_text(encoding="utf-8"))
            for dump in sorted((fixture_dir / ETHTOOL_SUBDIR).glob("*.txt"))
        ]
        got = bool(reports) and all(is_in_tree_driver(report) for report in reports)
        if got != expected["all_in_tree"]:
            mismatches.append(f"all_in_tree: got {got}, expected {expected['all_in_tree']}")

    if "determinism_stable" in expected:
        checked.append("determinism_stable")
        observations = _load_reboots(fixture_dir / REBOOTS_FILENAME)
        result = evaluate_determinism(observations, REQUIRED_REBOOT_CYCLES)
        if result.stable != expected["determinism_stable"]:
            mismatches.append(
                f"determinism_stable: got {result.stable}, "
                f"expected {expected['determinism_stable']}"
                + (f" ({'; '.join(result.drifts)})" if result.drifts else "")
            )

    return ReverifyReport(
        matched=not mismatches,
        checked=tuple(checked),
        mismatches=tuple(mismatches),
    )
