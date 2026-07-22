"""Offline orchestrator: run the synthetic harness, judge it, and write the artifact.

`python -m backend.rtbench.cli` runs the whole offline half of WP-1-04 end to end — it
drives the `WP-0C-06` synthetic harness (which auto-runs conditions 1-7), opens a
single torque-OFF, lock-held measurement session, and publishes the WP-1-04 artifact
with the `PG-RT-001a`/`PG-CAN-001`/`f_max` verdicts. The real-CAN inputs are deferred
and left absent, so the published figures are provisional by construction.

The lock is a real `flock` in a scratch directory here, because the VFS lock works
without a CAN stack (`02a` §4.1); on the rig it is the lock on the real channels.
"""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
from pathlib import Path
from typing import Any

from backend.can.lock.manager import LockManager
from backend.rtbench.publish import build_measurement_artifact
from backend.rtbench.session import ReadOnlyMeasurementSession, TorqueState
from sim.harness.conditions import MeasurementConfig
from sim.harness.harness import run_harness
from sim.harness.load_profile import LoadProfile

# The offline session's interfaces: the udev fixed names of the two front arms
# (`02` FR-CON-005). Offline the lock is a scratch flock over these names.
DEFAULT_IFACES = ("oa_fl", "oa_fr")

# The bimanual motor count the offline torque probe reports all-OFF over; on the rig
# the probe reads the follower's real per-motor enable state.
BIMANUAL_MOTOR_COUNT = 16


def _all_off_probe() -> TorqueState:
    """Return an all-OFF torque state over the bimanual motor set (offline fixture)."""
    return TorqueState(enabled=dict.fromkeys(range(BIMANUAL_MOTOR_COUNT), False))


def _readonly_connect() -> str:
    """Stand in for the rig's `connect_readonly()`; offline it opens nothing.

    Returns:
        (str) A marker naming what the real binding would be, so the single-connect
        counter measures a real call rather than a hardcoded value.
    """
    return "offline-dummy-binding (rig: WP-1-03 follower.connect_readonly)"


def _run(
    profile: LoadProfile, config: MeasurementConfig, host_id: str, lock_dir: str
) -> dict[str, Any]:
    """Run the offline measurement and assemble the artifact.

    Args:
        profile: The four-parameter synthetic load profile.
        config: The measurement config.
        host_id: The host the run executed on.
        lock_dir: Directory the scratch channel lock lives in.

    Returns:
        (dict[str, Any]) The published artifact.
    """
    manager = LockManager(lock_dir=lock_dir)
    acquired = manager.acquire_all(DEFAULT_IFACES)
    if not acquired.ok:
        raise RuntimeError(f"could not acquire the scratch channel lock: {acquired}")
    try:
        session = ReadOnlyMeasurementSession(
            manager=manager,
            ifaces=DEFAULT_IFACES,
            connect=_readonly_connect,
            torque_probe=_all_off_probe,
        )
        session.connect()
        result = run_harness(profile, config)
        return build_measurement_artifact(
            session=session,
            harness_result=result,
            host_id=host_id,
            is_fleet_target=False,
        )
    finally:
        manager.release_all()


def main(argv: list[str] | None = None) -> int:
    """Run the offline WP-1-04 measurement and print or write the artifact.

    Args:
        argv: Argument vector, or None to read `sys.argv`.

    Returns:
        (int) Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--streams", type=int, default=5)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--png-bytes", type=int, default=32 * 1024)
    parser.add_argument("--serialize-bytes", type=int, default=128 * 1024)
    parser.add_argument("--target-hz", type=float, default=200.0)
    parser.add_argument("--tick-count", type=int, default=1500)
    parser.add_argument("--host-id", default=platform.node() or "unknown")
    parser.add_argument("--lock-dir", default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    profile = LoadProfile(
        args.streams, args.width, args.height, args.png_bytes, args.serialize_bytes
    )
    config = MeasurementConfig(target_hz=args.target_hz, tick_count=args.tick_count)

    lock_dir = args.lock_dir
    if lock_dir is None:
        with tempfile.TemporaryDirectory(prefix="rtbench-lock-") as scratch:
            artifact = _run(profile, config, args.host_id, scratch)
    else:
        artifact = _run(profile, config, args.host_id, lock_dir)

    text = json.dumps(artifact, indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        verdict = artifact["pg_rt_001a"]
        print(f"PG-RT-001a: {verdict['status']} (provisional={verdict['provisional']})")
        print(f"f_max: {artifact['f_max']}")
        print(f"deferred: {artifact['deferred']['awaited_inputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
