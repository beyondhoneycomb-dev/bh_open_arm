"""Jog-latency bench — the per-target input to PG-IK-001 on the jog path (03 §5.11).

PG-IK-001 is a per-target gate: the jog's IK latency splits across the heterogeneous
fleet (Jetson Nano/Orin, RTX 5090/A6000), so a measurement on one host is not a fleet
verdict (NFR-TEL-004). This bench times whole jog *steps* — the frame math plus the
reused ``sim.ik`` solve — per target, and records honestly which target it actually ran
on. It fixes no numeric threshold; PG-IK-001 sets those after measurement.

The provenance machinery is reused from ``sim.ik.bench`` rather than re-typed: the host
fingerprint and the exact-target set are one definition, so a jog number and a raw-IK
number agree on where they were measured. On this host every fleet target is
``measured_on_target=False`` — this machine is an rtx_5080, not one of the four.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field

import numpy as np
from openarm_control.kinematics import IKParams

from backend.cartesian_jog.jog import (
    CartesianJog,
    JogAxis,
    JogCommand,
    JogKind,
    build_cartesian_jog,
)
from backend.cartesian_jog.tcp import TcpSelection
from sim.ik.bench import EXACT_TARGET_HOSTS, host_fingerprint
from targets.matrix import FLEET_TARGETS, load_matrix

# Default bench size — enough for a p50/p99 shape without a slow per-target run. Not a
# gate parameter; PG-IK-001 chooses its own N.
DEFAULT_STEPS = 32
DEFAULT_SEED = 0

# The jog cycle exercised: alternating small translations along each axis, which is the
# common teleop/jog motion the latency figure must cover.
_CYCLE_AXES = (JogAxis.X, JogAxis.Y, JogAxis.Z)


@dataclass(frozen=True)
class JogBenchResult:
    """One target's jog-latency measurement, tagged with its provenance.

    Attributes:
        target_id: The fleet target this run is labelled for.
        host: The machine the numbers were actually produced on.
        measured_on_target: Whether ``host`` is the labelled target (else deferred).
        steps: Number of jog steps timed.
        committed: Steps that advanced the committed pose (no hold).
        held: Steps that held instead of advancing.
        latency_ms_p50: Median jog-step latency in milliseconds, or None when empty.
        latency_ms_p99: p99 jog-step latency in milliseconds, or None when empty.
        note: Provenance note (why the per-target figure is deferred).
    """

    target_id: str
    host: str
    measured_on_target: bool
    steps: int
    committed: int
    held: int
    latency_ms_p50: float | None
    latency_ms_p99: float | None
    note: str = ""


@dataclass
class JogBenchRun:
    """A full PG-IK-001 jog-path run across the fleet.

    Attributes:
        host: The host all measurements were produced on.
        seed: The RNG seed used to sequence the jog cycle.
        results: One ``JogBenchResult`` per fleet target, in ``FLEET_TARGETS`` order.
    """

    host: str
    seed: int
    results: list[JogBenchResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view of the run (the PG-IK-001 input record)."""
        return {
            "host": self.host,
            "seed": self.seed,
            "fleet_targets": list(FLEET_TARGETS),
            "path": "cartesian_jog",
            "results": [asdict(result) for result in self.results],
        }


@contextlib.contextmanager
def _quiet_build() -> Iterator[None]:
    """Swallow openarm_control's construction-time debug prints (kinematics.py:160-161).

    The vendored solver prints its active-qpos and freeze-dof sets to stdout when a
    Kinematics is built. That upstream noise would corrupt the harness's JSON record on
    stdout; the library is not ours to edit, so it is silenced at the boundary.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _target_arch(target_id: str) -> str:
    """Return a fleet target's declared arch from the matrix, or ``?`` when absent."""
    for target in load_matrix().get("targets", []) or []:
        if str(target.get("target_id", "")) == target_id:
            return str(target.get("arch", "?"))
    return "?"


def _run_jog_cycle(jog: CartesianJog, steps: int, seed: int) -> tuple[list[float], int, int]:
    """Time ``steps`` jog steps, returning (latencies_ms, committed, held)."""
    rng = np.random.default_rng(seed)
    latencies_ms: list[float] = []
    committed = 0
    held = 0
    for index in range(steps):
        axis = _CYCLE_AXES[index % len(_CYCLE_AXES)]
        sign = 1 if rng.random() < 0.5 else -1
        command = JogCommand(
            side="right", kind=JogKind.TRANSLATION, axis=axis, sign=sign, tcp=TcpSelection.FLANGE
        )
        start = time.perf_counter()
        result = jog.step(command)
        latencies_ms.append((time.perf_counter() - start) * 1e3)
        if result.committed:
            committed += 1
        else:
            held += 1
            jog.resume()
    return latencies_ms, committed, held


def run_target_bench(
    target_id: str,
    steps: int = DEFAULT_STEPS,
    seed: int = DEFAULT_SEED,
    ik_params: IKParams | None = None,
) -> JogBenchResult:
    """Run the jog-latency bench for one fleet target and return its measured result.

    The computation is identical for every target — the hardware does not change on this
    host — so the result is tagged with the real host and ``measured_on_target``; it
    never relabels a local number as a fleet figure.

    Args:
        target_id: One of ``FLEET_TARGETS``.
        steps: Number of jog steps to time.
        seed: RNG seed sequencing the jog cycle.
        ik_params: mink IK parameters; None uses the defaults.

    Returns:
        (JogBenchResult) The target's measurement with provenance.

    Raises:
        ValueError: When ``target_id`` is not a fleet target.
    """
    if target_id not in FLEET_TARGETS:
        raise ValueError(f"unknown fleet target {target_id!r}; expected one of {FLEET_TARGETS}")

    with _quiet_build():
        jog = build_cartesian_jog(ik_params=ik_params)
    latencies_ms, committed, held = _run_jog_cycle(jog, steps, seed)

    host = host_fingerprint()
    measured = host in EXACT_TARGET_HOSTS
    note = (
        ""
        if measured
        else f"measured on {host}, not target {target_id} (arch {_target_arch(target_id)}); "
        "per-target figure deferred (NFR-TEL-004: an x86 number is not a fleet verdict)"
    )
    return JogBenchResult(
        target_id=target_id,
        host=host,
        measured_on_target=measured,
        steps=len(latencies_ms),
        committed=committed,
        held=held,
        latency_ms_p50=float(np.percentile(latencies_ms, 50)) if latencies_ms else None,
        latency_ms_p99=float(np.percentile(latencies_ms, 99)) if latencies_ms else None,
        note=note,
    )


def run_all_targets(
    steps: int = DEFAULT_STEPS, seed: int = DEFAULT_SEED, ik_params: IKParams | None = None
) -> JogBenchRun:
    """Run the jog bench across every fleet target."""
    run = JogBenchRun(host=host_fingerprint(), seed=seed)
    for target_id in FLEET_TARGETS:
        run.results.append(run_target_bench(target_id, steps, seed, ik_params))
    return run


def main(argv: list[str] | None = None) -> int:
    """Run the jog bench and print the PG-IK-001 input record as JSON.

    Returns:
        (int) 0 always — the harness measures, it renders no pass/fail verdict.
    """
    parser = argparse.ArgumentParser(
        description="Cartesian jog latency bench (PG-IK-001 per-target input)."
    )
    parser.add_argument(
        "--target", choices=[*FLEET_TARGETS, "all"], default="all", help="Fleet target, or 'all'."
    )
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help="Jog steps per target.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Jog-cycle RNG seed.")
    args = parser.parse_args(argv)

    if args.target == "all":
        record: dict[str, object] = run_all_targets(args.steps, args.seed).to_dict()
    else:
        result = run_target_bench(args.target, args.steps, args.seed)
        record = {"host": host_fingerprint(), "seed": args.seed, "results": [asdict(result)]}

    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
