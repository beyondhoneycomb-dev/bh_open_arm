"""The live M-1 measurement orchestrator — deferred until a real adapter exists.

This wires the parsers and computers together against real tools: `lsusb -t` for the
topology, `ip -s -d link show` for the bus statistics, and the `motor_sampling_check`
frequency sweep for RTT / `f_max_can` / frames-per-cycle. It shells out to those
tools (no CAN library is imported — the dependency-separation boundary keeps this
module free of the robot stack) and publishes a `HARDWARE_CAPTURE` artifact, but
only while the `WP-0B-01` flock is held.

None of it runs on this host: there is no CAN adapter and no `motor_sampling_check`
binary here, so `real_measurement_available` returns False and the bound test skips
with a reason. The code is complete and typed so that on the rig it runs unchanged,
and so that the re-verification hook can exercise the same parse chain against a
captured log the moment one is supplied.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from backend.can.lock.manager import LockManager
from ops.hw.usb.artifact import ArtifactSource, MeasurementArtifact, publish_artifact
from ops.hw.usb.distribution import compute_distribution
from ops.hw.usb.fmax import compute_fmax
from ops.hw.usb.frames import record_frames_per_cycle
from ops.hw.usb.hol import build_hol_report
from ops.hw.usb.iplink import parse_bus_stats
from ops.hw.usb.sampling import parse_run
from ops.hw.usb.topology import CAN_ADAPTER_DRIVER, parse_topology

# Environment override naming the (modified) M-1 sweep tool. Absent on this host, so
# the availability probe fails closed and the live path is never taken here.
MSC_BINARY_ENV = "OPENARM_MSC_BIN"
_MSC_DEFAULT_NAME = "motor_sampling_check"
# The sweep grid `15` §2.10 M-1 prescribes.
DEFAULT_SWEEP_HZ = (100, 200, 300, 400, 500, 600, 700, 750, 800, 900, 1000)
_TOOL_TIMEOUT_S = 30


def real_measurement_available() -> bool:
    """Report whether a real M-1 measurement can run on this host.

    True requires both the sweep tool (via `OPENARM_MSC_BIN` or on `PATH`) and the
    `lsusb`/`ip` utilities to be present, *and* a `gs_usb` CAN adapter to be visible
    in the topology. Any missing piece fails closed, which is why this returns False
    on a desktop with no adapter and the live acceptances defer rather than fake.

    Returns:
        (bool) True only when the rig tooling and a CAN adapter are both present.
    """
    if _msc_binary() is None:
        return False
    if shutil.which("lsusb") is None or shutil.which("ip") is None:
        return False
    try:
        topology = parse_topology(_run(["lsusb", "-t"]))
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(topology.adapters)


def run_live_measurement(
    manager: LockManager,
    ifaces: Sequence[str],
    out_path: Path,
    sweep_hz: Sequence[int] = DEFAULT_SWEEP_HZ,
) -> Path:
    """Run the full M-1 measurement against real tools and publish the artifact.

    Order matters and is enforced by `publish_artifact`: the flock must be held or
    the artifact is refused. RTT samples are pooled across the sweep for the overall
    distribution; `f_max_can` is computed per interface from that interface's sweep;
    frames-per-cycle is pooled for the `PG-CAN-001` verdict.

    Args:
        manager: Lock manager that must hold every interface in `ifaces`.
        ifaces: The arms' CAN interfaces to sweep and measure.
        out_path: Destination for the published artifact JSON.
        sweep_hz: The target frequencies to sweep.

    Returns:
        (Path) `out_path`, once the artifact is published.

    Raises:
        MeasurementRefusedError: If the flock is not held (raised by publish).
        RuntimeError: If the sweep tool is unavailable.
    """
    binary = _msc_binary()
    if binary is None:
        raise RuntimeError(f"{_MSC_DEFAULT_NAME} not found; set {MSC_BINARY_ENV}")

    topology = parse_topology(_run(["lsusb", "-t"]), adapter_driver=CAN_ADAPTER_DRIVER)
    bus_stats = tuple(
        parse_bus_stats(iface, _run(["ip", "-s", "-d", "link", "show", iface])) for iface in ifaces
    )

    rtt_us: list[float] = []
    frames: list[int] = []
    fmax_per_arm = []
    for iface in ifaces:
        sweep: dict[int, float] = {}
        for target in sweep_hz:
            run = parse_run(_run([binary, "--all", str(target), iface, "-fd"]))
            rtt_us.extend(run.rtt_us)
            frames.extend(run.frames_per_cycle)
            if run.actual_hz is not None:
                sweep[target] = run.actual_hz
        fmax_per_arm.append(compute_fmax(iface, sweep))

    artifact = MeasurementArtifact(
        source=ArtifactSource.HARDWARE_CAPTURE,
        topology=topology,
        rtt=compute_distribution(rtt_us, unit="us"),
        fmax_per_arm=tuple(fmax_per_arm),
        frames=record_frames_per_cycle(frames),
        bus_stats=bus_stats,
        hol=build_hol_report(),
    )
    publish_artifact(manager, ifaces, artifact, out_path)
    return out_path


def _msc_binary() -> str | None:
    """Resolve the sweep tool from the env override or `PATH`, or None when absent."""
    override = os.environ.get(MSC_BINARY_ENV)
    if override:
        return override if Path(override).is_file() else None
    return shutil.which(_MSC_DEFAULT_NAME)


def _run(argv: list[str]) -> str:
    """Run a tool and return its stdout, raising on failure.

    Args:
        argv: Command and arguments.

    Returns:
        (str) Captured stdout.
    """
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=_TOOL_TIMEOUT_S,
        check=True,
    )
    return completed.stdout
