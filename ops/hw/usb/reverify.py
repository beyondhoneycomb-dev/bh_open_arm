"""Real-fixture re-verification hook for `WP-0B-06` (plan 02a §4.1).

The parsers and computers run here against synthetic fixtures, which proves the
maths and the grammar but not that they match what a *real* adapter and a *real*
`motor_sampling_check` emit. That end-to-end claim needs hardware this host does not
have, so it is deferred — but the deferral is required to ship this hook, so the
moment a directory of real captures is supplied the identical parse chain re-runs
against the real bytes.

The hook is not a stub: `reverify_from_fixture` drives the same `parse_topology` /
`parse_bus_stats` / `parse_run` this codebase uses live, over whatever files the
capture directory holds, and reports what it found. The bound test skips with a
reason until `OPENARM_USB_REAL_FIXTURE` names such a directory, whose layout is:

    lsusb_t.txt                 (raw `lsusb -t`)
    ip_s_d_<iface>.txt          (raw `ip -s -d link show <iface>`, one per arm)
    msc_<iface>_<hz>.log        (raw `motor_sampling_check` run, per arm per target)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ops.hw.usb.fmax import FmaxResult, compute_fmax
from ops.hw.usb.frames import FramesPerCycle, record_frames_per_cycle
from ops.hw.usb.iplink import CanBusStats, parse_bus_stats
from ops.hw.usb.sampling import parse_run
from ops.hw.usb.topology import TopologyReport, parse_topology

# Environment variable a caller sets to point the hook at a real capture directory.
FIXTURE_ENV_VAR = "OPENARM_USB_REAL_FIXTURE"
_TOPOLOGY_FILE = "lsusb_t.txt"
_IP_STATS = re.compile(r"^ip_s_d_(?P<iface>[A-Za-z0-9_.-]+)\.txt$")
_MSC_LOG = re.compile(r"^msc_(?P<iface>[A-Za-z0-9_.-]+)_(?P<hz>\d+)\.log$")


@dataclass(frozen=True)
class ReverifyResult:
    """The outcome of re-running the parse chain over a real capture directory.

    Attributes:
        topology: The parsed USB topology, or None when no `lsusb_t.txt` was present.
        bus_stats: Per-interface bus statistics parsed from the real `ip -s -d` dumps.
        fmax_per_arm: Per-interface `f_max_can` recomputed from the real sweep logs.
        frames: The frames-per-cycle record recomputed from the real sweep logs.
    """

    topology: TopologyReport | None
    bus_stats: tuple[CanBusStats, ...]
    fmax_per_arm: tuple[FmaxResult, ...]
    frames: FramesPerCycle


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def reverify_from_fixture(fixture_dir: Path) -> ReverifyResult:
    """Re-run the live parse chain over a directory of real captured tool output.

    This is the identical parsing the live path uses, pointed at real bytes: the
    topology parser over the captured `lsusb -t`, the bus-stats parser over each
    captured `ip -s -d` dump, and the sweep parser over each captured
    `motor_sampling_check` log, from which `f_max_can` and frames-per-cycle are
    recomputed. A format drift in the real tool surfaces here as a parse that finds
    nothing, which is exactly the signal the deferral exists to catch.

    Args:
        fixture_dir: Directory of captured tool output (see module docstring).

    Returns:
        (ReverifyResult) The re-derived topology, bus stats, per-arm `f_max_can`,
        and frames-per-cycle record.
    """
    topology = None
    topology_path = fixture_dir / _TOPOLOGY_FILE
    if topology_path.is_file():
        topology = parse_topology(topology_path.read_text(encoding="utf-8"))

    bus_stats: list[CanBusStats] = []
    sweeps: dict[str, dict[int, float]] = {}
    frame_counts: list[int] = []

    for entry in sorted(fixture_dir.iterdir()):
        stats_match = _IP_STATS.match(entry.name)
        if stats_match:
            bus_stats.append(
                parse_bus_stats(stats_match.group("iface"), entry.read_text(encoding="utf-8"))
            )
            continue
        log_match = _MSC_LOG.match(entry.name)
        if log_match:
            run = parse_run(entry.read_text(encoding="utf-8"))
            frame_counts.extend(run.frames_per_cycle)
            if run.actual_hz is not None:
                sweeps.setdefault(log_match.group("iface"), {})[int(log_match.group("hz"))] = (
                    run.actual_hz
                )

    fmax_per_arm = tuple(compute_fmax(iface, sweeps[iface]) for iface in sorted(sweeps))
    return ReverifyResult(
        topology=topology,
        bus_stats=tuple(bus_stats),
        fmax_per_arm=fmax_per_arm,
        frames=record_frames_per_cycle(frame_counts),
    )
