"""Per-target IK/inference bench-runner harness (CG-4B-04e, `03` §5.11, `NFR-PRF-048`).

`PG-IK-001` is a per-target gate: IK p50/p99, the unconstrained-fallback count and the
collision-check latency must be measured on each target's own hardware, because
`NFR-TEL-004` forbids treating one host's x86 numbers as a fleet verdict. This harness
produces that input record per target and records, honestly, which target it actually
measured on. On this box every fleet target is measured-off (this machine is an rtx_5080,
`targets/matrix.yaml`, not one of the four), so every per-target figure is `DEFERRED` —
the harness proves it RUNS here and defers the target numbers rather than relabelling a
local measurement as a fleet result.

It reuses rather than restates its two measurements:

  * IK p50/p99 + unconstrained-fallback count come from the committed WP-0C-02 harness
    (`sim.ik.bench`), which already samples reachable EE targets by a seeded FK
    round-trip and defers per target honestly;
  * collision-check latency is timed here over the committed WP-0C-03 cell asset
    (`sim.ik.asset`) — `mj_collision` after `mj_kinematics` on random in-limit configs.

The one gate branch this harness can decide without the target is the safety one: an
unconstrained-fallback firing is `FAIL_BLOCKING` regardless of host (`03` §5.11), because
a limit-violating solution is a safety defect, not a performance shortfall. Everything
else stays `DEFERRED`.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass

import mujoco
import numpy as np

from backend.compat.deploy_matrix.block_matrix import IkGateStatus
from backend.compat.deploy_matrix.target import DeploymentTarget, recognize_target
from sim.ik.asset import fixed_cell_xml
from sim.ik.bench import (
    DEFAULT_SAMPLES,
    DEFAULT_SEED,
    EXACT_TARGET_HOSTS,
    BenchResult,
    host_fingerprint,
    run_target_bench,
)

# Collision-latency sample count — enough for a p50/p99 shape without slowing the harness
# per target. Not a gate parameter; PG-IK-001 chooses its own N after measurement.
DEFAULT_COLLISION_SAMPLES = 64


@dataclass(frozen=True)
class CollisionLatency:
    """Collision-check latency over the committed cell asset, with provenance.

    Attributes:
        samples: Number of `mj_collision` calls timed.
        p50_ms: Median collision-check latency in milliseconds, or None when empty.
        p99_ms: p99 collision-check latency in milliseconds, or None when empty.
        max_contacts: The largest contact count seen across samples — evidence the
            collision phase actually did work rather than timing an empty scene.
    """

    samples: int
    p50_ms: float | None
    p99_ms: float | None
    max_contacts: int


@dataclass(frozen=True)
class DeployTargetBench:
    """One target's combined IK + collision bench, tagged with measurement provenance.

    Attributes:
        target: The fleet target this run is labelled for.
        host: The machine the numbers were actually produced on.
        measured_on_target: Whether `host` is the labelled target; False keeps the
            per-target figure deferred.
        ik: The WP-0C-02 IK bench result (p50/p99 + unconstrained-fallback count).
        collision: The collision-check latency measured over the cell asset.
        ik_gate: The `PG-IK-001` status — `FAIL_BLOCKING` on any fallback firing (safety,
            host-independent), else `DEFERRED` until measured on the target.
        note: Human-readable provenance (why the figure is deferred).
    """

    target: str
    host: str
    measured_on_target: bool
    ik: BenchResult
    collision: CollisionLatency
    ik_gate: str
    note: str


@contextlib.contextmanager
def _quiet_stdout() -> Iterator[None]:
    """Swallow the vendored solver's build-time debug prints during a bench run.

    `openarm_control`'s `_IKSolver` prints its active-qpos/freeze-dof sets to stdout on
    construction (kinematics.py:160-161); that upstream noise would corrupt this
    harness's JSON on stdout, and the library is not ours to edit, so it is silenced at
    the boundary.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def measure_collision_latency(
    samples: int = DEFAULT_COLLISION_SAMPLES, seed: int = DEFAULT_SEED
) -> CollisionLatency:
    """Time `mj_collision` over the committed cell asset on random in-limit configs.

    The model is the WP-0C-03 fixed cell (`sim.ik.asset`), READ only. Each sample draws a
    random configuration within the limited joints' `jnt_range`, updates kinematics, then
    times the collision phase alone (`mj_collision`), so the number is collision-check
    latency rather than a full forward step.

    Args:
        samples: Number of collision checks to time.
        seed: RNG seed for the random configurations.

    Returns:
        (CollisionLatency) The p50/p99 latency and the largest contact count observed.
    """
    model = mujoco.MjModel.from_xml_path(str(fixed_cell_xml()))
    data = mujoco.MjData(model)
    rng = np.random.default_rng(seed)
    lower = model.jnt_range[:, 0].copy()
    upper = model.jnt_range[:, 1].copy()
    limited = model.jnt_limited.astype(bool)

    latencies_ms: list[float] = []
    max_contacts = 0
    for _ in range(samples):
        qpos = data.qpos.copy()
        for joint_index in range(model.njnt):
            address = model.jnt_qposadr[joint_index]
            if limited[joint_index] and upper[joint_index] > lower[joint_index]:
                qpos[address] = rng.uniform(lower[joint_index], upper[joint_index])
        data.qpos[:] = qpos
        mujoco.mj_kinematics(model, data)
        start = time.perf_counter()
        mujoco.mj_collision(model, data)
        latencies_ms.append((time.perf_counter() - start) * 1e3)
        max_contacts = max(max_contacts, int(data.ncon))

    return CollisionLatency(
        samples=len(latencies_ms),
        p50_ms=float(np.percentile(latencies_ms, 50)) if latencies_ms else None,
        p99_ms=float(np.percentile(latencies_ms, 99)) if latencies_ms else None,
        max_contacts=max_contacts,
    )


def _ik_gate_status(ik: BenchResult, measured_on_target: bool) -> IkGateStatus:
    """Derive the `PG-IK-001` status from a bench result (`03` §5.11).

    The safety branch is host-independent: any unconstrained-fallback firing is
    `FAIL_BLOCKING`, because it means IK produced a limit-ignoring solution. The
    performance verdict (p99 vs the target budget) needs the target's own hardware, so
    absent that it is `DEFERRED` rather than a fabricated pass.

    Args:
        ik: The IK bench result to judge.
        measured_on_target: Whether the run was on the labelled target's hardware.

    Returns:
        (IkGateStatus) `FAIL_BLOCKING` on any fallback firing, else `DEFERRED`.
    """
    if ik.fallback_firings > 0:
        return IkGateStatus.FAIL_BLOCKING
    if not measured_on_target:
        return IkGateStatus.DEFERRED
    return IkGateStatus.PASS


def run_deploy_bench(
    target: DeploymentTarget,
    ik_samples: int = DEFAULT_SAMPLES,
    collision_samples: int = DEFAULT_COLLISION_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> DeployTargetBench:
    """Run the combined IK + collision bench for one fleet target.

    Args:
        target: The deployment target to label the run for.
        ik_samples: IK solves to time (delegated to `sim.ik.bench`).
        collision_samples: Collision checks to time.
        seed: RNG seed shared by both measurements.

    Returns:
        (DeployTargetBench) The target's combined result with measurement provenance.
    """
    with _quiet_stdout():
        ik = run_target_bench(target.value, samples=ik_samples, seed=seed)
        collision = measure_collision_latency(samples=collision_samples, seed=seed)

    host = host_fingerprint()
    measured_on_target = host in EXACT_TARGET_HOSTS
    gate = _ik_gate_status(ik, measured_on_target)
    note = (
        ""
        if measured_on_target
        else (
            f"measured on {host}, not target {target.value}; per-target IK/collision "
            "figures deferred (NFR-TEL-004: an x86 number is not a fleet verdict). "
            "Fallback-firing safety check ran here and is host-independent."
        )
    )
    return DeployTargetBench(
        target=target.value,
        host=host,
        measured_on_target=measured_on_target,
        ik=ik,
        collision=collision,
        ik_gate=gate.value,
        note=note,
    )


def run_all(
    ik_samples: int = DEFAULT_SAMPLES,
    collision_samples: int = DEFAULT_COLLISION_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> list[DeployTargetBench]:
    """Run the combined bench across every deployment target.

    Args:
        ik_samples: IK solves per target.
        collision_samples: Collision checks per target.
        seed: RNG seed shared across targets.

    Returns:
        (list[DeployTargetBench]) One result per target, in `DeploymentTarget` order.
    """
    return [
        run_deploy_bench(target, ik_samples, collision_samples, seed) for target in DeploymentTarget
    ]


def _to_record(benches: list[DeployTargetBench]) -> dict[str, object]:
    """Return a JSON-serialisable view of a bench run (the CG-4B-04e input record)."""
    return {
        "host": host_fingerprint(),
        "targets": [target.value for target in DeploymentTarget],
        "results": [asdict(bench) for bench in benches],
    }


def main(argv: list[str] | None = None) -> int:
    """Run the bench and print the CG-4B-04e input record as JSON.

    Args:
        argv: CLI arguments; None reads `sys.argv`.

    Returns:
        (int) 0 always — the harness measures, it does not render a pass/fail verdict.
    """
    parser = argparse.ArgumentParser(
        description="Per-target IK/inference bench harness (CG-4B-04e input)."
    )
    parser.add_argument(
        "--target",
        default="all",
        help="Deployment target to bench, or 'all' (default).",
    )
    parser.add_argument(
        "--ik-samples", type=int, default=DEFAULT_SAMPLES, help="IK solves per target."
    )
    parser.add_argument(
        "--collision-samples",
        type=int,
        default=DEFAULT_COLLISION_SAMPLES,
        help="Collision checks per target.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Shared RNG seed.")
    args = parser.parse_args(argv)

    if args.target == "all":
        benches = run_all(args.ik_samples, args.collision_samples, args.seed)
    else:
        target = recognize_target(args.target)
        benches = [run_deploy_bench(target, args.ik_samples, args.collision_samples, args.seed)]

    print(json.dumps(_to_record(benches), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
