"""Real-fixture re-verification hook for the boot-bound acceptances ①④ (plan 02a §4.1).

Two WP-OPS-02 acceptances can only be observed after a real boot on real hardware, so they
are `SHAPE-MS` and deferred on this host: ① that the four fixed names come up with `fd on`,
the verified bitrates and `txqueuelen 1000`, and ④ that ten reboots bind the names to the
same physical channels. Neither is asserted green here and neither is dropped — they wait
behind this hook.

When a directory of real captures is supplied (via `OPENARM_OPS02_REAL_FIXTURE` or an
explicit path), the hook re-runs the *same* evaluators the offline tests use — WP-0B-02's
`ip -details link show` parser for ① and WP-0B-05's determinism evaluator for ④, the shared
evidence acceptance ④ names — now pointed at real bytes. The capture directory holds:

- `linkshow/<name>.txt`  — one `ip -details link show <iface>` dump per fixed name.
- `reboots.json`         — `[{"reboot_index": int, "bindings": {name: channel_key}}, ...]`.
- `expected.json`        — recorded truth: `link_ok`, `determinism_stable` (each optional;
                           only supplied keys are checked).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from backend.can.link.parser import LinkState, parse_link_show
from ops.hw.udev.determinism import (
    REQUIRED_REBOOT_CYCLES,
    RebootObservation,
    evaluate_determinism,
)
from ops.systemd.constants import LINK_BITRATE, LINK_DBITRATE, LINK_TXQUEUELEN

FIXTURE_ENV_VAR = "OPENARM_OPS02_REAL_FIXTURE"
EXPECTED_FILENAME = "expected.json"
LINKSHOW_SUBDIR = "linkshow"
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


def link_params_ok(state: LinkState) -> bool:
    """Whether a measured link carries the exact parameters the unit was to set.

    The unit and this check read the same constants, so a link that came up wrong — CAN 2.0,
    a mis-set bitrate, or the kernel-default queue length — fails here. `txqueuelen` is
    included because the whole point of acceptance ① is that the unit raised it; the backend
    verifier (WP-0B-02) treats it only as advisory.

    Args:
        state: A parsed `ip -details link show` result.

    Returns:
        (bool) True when fd, bitrate, dbitrate and txqueuelen all match the intended values.
    """
    return (
        state.fd
        and state.bitrate == LINK_BITRATE
        and state.dbitrate == LINK_DBITRATE
        and state.txqueuelen == LINK_TXQUEUELEN
    )


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

    Only the expectations recorded in `expected.json` are evaluated, so a partial capture
    (link dumps but no reboot log, or the reverse) verifies what it can and stays silent on
    the rest.

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

    checked: list[str] = []
    mismatches: list[str] = []

    if "link_ok" in expected:
        checked.append("link_ok")
        dumps = sorted((fixture_dir / LINKSHOW_SUBDIR).glob("*.txt"))
        states = [parse_link_show(dump.read_text(encoding="utf-8"), dump.stem) for dump in dumps]
        got = bool(states) and all(link_params_ok(state) for state in states)
        if got != expected["link_ok"]:
            mismatches.append(f"link_ok: got {got}, expected {expected['link_ok']}")

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
