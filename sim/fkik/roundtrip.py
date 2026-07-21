"""FK<->IK round-trip regression harness (WP-0C-04).

The contract is a round trip: ``q -> FK -> p -> IK -> q'``, with the EE residual
``‖p − FK(q')‖`` characterised over a sample of joint configurations. The harness
produces the residual *distribution* and a histogram; it fixes no pass/fail
threshold — PG-IK-001 sets that number after measurement (acceptance ⑥). It is a
regression tripwire for the plumbing this WP guards: the name-resolved index map,
the EE-frame convention, and the rad<->deg crossing. A break in any of those makes
the round-trip residual jump, whatever the solver does.

IK runs through the WP-0C-02 ``IkAdapter``, seeded (warm-started) at the sampled
configuration so the residual isolates *round-trip fidelity* from global convergence
— convergence from a distant seed is a solver-tuning question owned by PG-IK-001's
latency bench, not the round-trip contract.

Honest environment gap: the only QP solver installed here is ``daqp``, and its
constrained solve (the ``ConfigurationLimit`` QP) reports infeasible for this model
on every sample — so the safety-default adapter (unconstrained fallback *disabled*)
holds 100% of the time and produces no residuals. To characterise the round trip at
all in this environment, the distribution pass enables the unconstrained fallback
and records every firing as provenance (``fallback_firings``); the note on each
report states that the residuals came through the fallback because the constrained
solver was infeasible. The constrained-only behaviour is not hidden — it is the
honest 100%-hold state a caller sees when ``allow_unconstrained_fallback=False``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import platform
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
from openarm_control.kinematics import IKParams

from sim.ik.adapter import BIMANUAL_WIDTH, SIDE_WIDTH, IkAdapter, build_ik_adapter
from sim.ik.faults import IkFaultCode
from sim.ik.limits import all_soft_limits

# Sample count large enough to show a p50/p99 shape without making the harness slow;
# not a gate parameter, PG-IK-001 chooses its own N (acceptance ⑥).
DEFAULT_SAMPLES = 64
DEFAULT_SEED = 0
DEFAULT_HISTOGRAM_BINS = 20

# Interior samples are drawn from a centred fraction of each joint's soft-limit span,
# so the commanded poses sit where the arm actually works rather than pinned to the
# limits; near-limit samples (acceptance ⑤) are drawn deliberately at the boundary.
INTERIOR_SPAN_FRACTION = 0.5
NEAR_LIMIT_MARGIN_FRACTION = 0.02

# The tuning `16` §10.1 records for production IK. max_iters is raised from the
# openarm_control default of 5 to the documented bimanual value so the harness
# characterises the configured solver, not the library default.
_DEFAULT_MAX_ITERS = 10
_DEFAULT_DT = 0.1
_DEFAULT_DAMPING = 0.1
_DEFAULT_POSTURE_COST = 0.01
_DEFAULT_LM_DAMPING = 0.01

# In-limit tolerance in radians; absorbs solver float error, never a genuine escape.
IN_LIMIT_TOLERANCE_RAD = 1e-6

# Pose layout: the first three components are the EE position the residual measures.
_POSITION_DIM = 3


def default_ik_params() -> IKParams:
    """Return a fresh IKParams carrying the documented production tuning."""
    return IKParams(
        max_iters=_DEFAULT_MAX_ITERS,
        dt=_DEFAULT_DT,
        damping=_DEFAULT_DAMPING,
        posture_cost=_DEFAULT_POSTURE_COST,
        lm_damping=_DEFAULT_LM_DAMPING,
    )


@dataclass(frozen=True)
class RoundTripSample:
    """One ``q -> FK -> p -> IK -> q'`` round trip.

    ``solution_produced`` and ``adapter_held`` are distinct on purpose: when the
    unconstrained fallback fires it yields a solution *and* raises a fault, so the
    adapter holds (``adapter_held=True``) while a solution still exists to measure
    (``solution_produced=True``). The residual is defined whenever a solution exists,
    regardless of the hold.

    Attributes:
        index: 0-based sample index.
        solution_produced: Whether IK returned a joint solution (via either path).
        adapter_held: Whether the adapter held its last-valid pose (any fault, incl.
            each fallback firing, forces a hold — provenance, not solution presence).
        fallback_firings: Unconstrained-fallback firings this solve (OA-IK-003).
        clamp_firings: Joint-limit clamps this solve (OA-IK-004).
        residual_right_m: Right-arm EE residual ‖p − FK(q')‖ in metres, or None.
        residual_left_m: Left-arm EE residual in metres, or None.
        raw_solution_in_limits: Whether the solution lay inside the soft limits before
            any clamp, or None when no solution was produced.
    """

    index: int
    solution_produced: bool
    adapter_held: bool
    fallback_firings: int
    clamp_firings: int
    residual_right_m: float | None
    residual_left_m: float | None
    raw_solution_in_limits: bool | None

    def residuals(self) -> tuple[float, ...]:
        """Return the per-arm residuals present in this sample (empty when none)."""
        if self.residual_right_m is None or self.residual_left_m is None:
            return ()
        return (self.residual_right_m, self.residual_left_m)


@dataclass
class RoundTripReport:
    """The distribution and provenance of a round-trip run.

    Attributes:
        host: The machine the run was produced on.
        seed: RNG seed for the sampled configurations.
        samples: Number of round trips attempted.
        allow_unconstrained_fallback: Whether the fallback was enabled for the run.
        seed_perturbation_rad: Warm-start perturbation used (0 = exact warm start).
        results: One ``RoundTripSample`` per configuration.
        note: Provenance note (why residuals came through the fallback, if they did).
    """

    host: str
    seed: int
    samples: int
    allow_unconstrained_fallback: bool
    seed_perturbation_rad: float
    results: list[RoundTripSample] = field(default_factory=list)
    note: str = ""

    def all_residuals_m(self) -> np.ndarray:
        """Return every per-arm residual across solved samples as a flat array."""
        flat: list[float] = []
        for sample in self.results:
            flat.extend(sample.residuals())
        return np.array(flat, dtype=float)

    def solved_count(self) -> int:
        """Return how many samples produced an IK solution (via either path)."""
        return sum(1 for sample in self.results if sample.solution_produced)

    def adapter_held_count(self) -> int:
        """Return how many samples left the adapter holding (a fault fired)."""
        return sum(1 for sample in self.results if sample.adapter_held)

    def fallback_firings(self) -> int:
        """Return the total unconstrained-fallback firings across the run."""
        return sum(sample.fallback_firings for sample in self.results)

    def clamp_firings(self) -> int:
        """Return the total joint-limit clamps across the run."""
        return sum(sample.clamp_firings for sample in self.results)

    def percentiles(self) -> dict[str, float | None]:
        """Return the residual distribution's summary percentiles in metres.

        Returns:
            (dict) p50/p90/p95/p99/min/max/mean, each None when no residual exists.
        """
        residuals = self.all_residuals_m()
        if residuals.size == 0:
            return dict.fromkeys(("p50", "p90", "p95", "p99", "min", "max", "mean"))
        return {
            "p50": float(np.percentile(residuals, 50)),
            "p90": float(np.percentile(residuals, 90)),
            "p95": float(np.percentile(residuals, 95)),
            "p99": float(np.percentile(residuals, 99)),
            "min": float(residuals.min()),
            "max": float(residuals.max()),
            "mean": float(residuals.mean()),
        }

    def histogram(self, bins: int = DEFAULT_HISTOGRAM_BINS) -> str:
        """Return an ASCII histogram of the residual distribution (acceptance ①)."""
        return format_histogram(self.all_residuals_m(), bins)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view of the report."""
        return {
            "host": self.host,
            "seed": self.seed,
            "samples": self.samples,
            "solved": self.solved_count(),
            "adapter_held": self.adapter_held_count(),
            "allow_unconstrained_fallback": self.allow_unconstrained_fallback,
            "fallback_firings": self.fallback_firings(),
            "clamp_firings": self.clamp_firings(),
            "seed_perturbation_rad": self.seed_perturbation_rad,
            "residual_percentiles_m": self.percentiles(),
            "residual_count": int(self.all_residuals_m().size),
            "histogram": self.histogram().splitlines(),
            "note": self.note,
        }


@contextlib.contextmanager
def _quiet_build() -> Iterator[None]:
    """Swallow openarm_control's build-time debug prints (kinematics.py:160-161).

    The vendored ``_IKSolver`` prints its active-qpos and freeze-dof sets to stdout
    at construction. That is upstream noise, not this harness's output, and it
    corrupts the JSON the CLI writes to stdout; the library is not ours to edit, so
    it is silenced at the boundary.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _limit_bounds() -> tuple[np.ndarray, np.ndarray]:
    """Return the (lower, upper) soft-limit bounds in radians, arm-major float[16]."""
    limits = all_soft_limits()
    lower = np.array([limit.lower_rad.value for limit in limits], dtype=float)
    upper = np.array([limit.upper_rad.value for limit in limits], dtype=float)
    return lower, upper


def sample_interior_configs(count: int, seed: int) -> np.ndarray:
    """Sample joint configurations inside a centred fraction of the soft limits.

    Args:
        count: Number of configurations to draw.
        seed: RNG seed for reproducibility.

    Returns:
        (np.ndarray) A ``(count, 16)`` array of radian configurations.
    """
    lower, upper = _limit_bounds()
    mid = 0.5 * (lower + upper)
    span = INTERIOR_SPAN_FRACTION * (upper - lower)
    rng = np.random.default_rng(seed)
    offsets = (rng.random((count, BIMANUAL_WIDTH)) - 0.5) * span
    return np.clip(mid + offsets, lower, upper)


def sample_near_limit_configs(count: int, seed: int) -> np.ndarray:
    """Sample configurations pinned near each joint's soft-limit boundary.

    Each joint is placed a hair inside either its lower or its upper bound, so the
    round trip commands poses at the edge of the reachable set — the case
    acceptance ⑤ checks the IK solution stays inside the limits for.

    Args:
        count: Number of configurations to draw.
        seed: RNG seed for reproducibility.

    Returns:
        (np.ndarray) A ``(count, 16)`` array of radian configurations.
    """
    lower, upper = _limit_bounds()
    margin = NEAR_LIMIT_MARGIN_FRACTION * (upper - lower)
    rng = np.random.default_rng(seed)
    pick_upper = rng.random((count, BIMANUAL_WIDTH)) < 0.5
    configs = np.where(pick_upper, upper - margin, lower + margin)
    return np.clip(configs, lower, upper)


def _forward_pose(adapter: IkAdapter, config: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Forward-kinematics a 16-value configuration to (right, left) EE poses.

    FK runs through the adapter's own kinematics rather than a second model: the
    round-trip target and the achieved pose must both be evaluated on exactly the
    jnt_range-overridden model IK solves on, or the residual would compare poses
    across two models. The adapter exposes no public FK, so its kinematics is used
    directly.

    Args:
        adapter: A built IK adapter.
        config: Radian configuration, float[16] = right[8] + left[8].

    Returns:
        (tuple[np.ndarray, np.ndarray]) The (right, left) EE poses.
    """
    right = np.asarray(config[:SIDE_WIDTH], dtype=float)
    left = np.asarray(config[SIDE_WIDTH:], dtype=float)
    return adapter._kin.fk_bimanual(right, left)


def _solution_in_limits(solution: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> bool:
    """Return whether an arm-major radian solution lies within the soft limits."""
    arm = solution[:BIMANUAL_WIDTH]
    return bool(
        np.all(arm >= lower - IN_LIMIT_TOLERANCE_RAD)
        and np.all(arm <= upper + IN_LIMIT_TOLERANCE_RAD)
    )


def run_round_trip(
    adapter: IkAdapter,
    index: int,
    config: np.ndarray,
    seed_perturbation_rad: float,
    rng: np.random.Generator,
) -> RoundTripSample:
    """Run one ``q -> FK -> p -> IK -> q'`` round trip and measure its EE residual.

    Args:
        adapter: A built IK adapter (its fallback policy governs whether it solves).
        index: 0-based sample index for the result.
        config: The sampled configuration q, float[16] radians.
        seed_perturbation_rad: Std-dev of a Gaussian perturbation added to the IK
            warm-start seed; 0 seeds exactly at q.
        rng: RNG used for the seed perturbation (kept out of the sampling stream).

    Returns:
        (RoundTripSample) The round trip's residuals and fault provenance.
    """
    lower, upper = _limit_bounds()
    target_right, target_left = _forward_pose(adapter, config)

    seed = config.astype(np.float32)
    if seed_perturbation_rad > 0.0:
        noise = rng.normal(0.0, seed_perturbation_rad, BIMANUAL_WIDTH)
        seed = np.clip(config + noise, lower, upper).astype(np.float32)

    adapter.sync(seed)
    adapter.set_target("right", target_right)
    adapter.set_target("left", target_left)
    outcome = adapter.solve()

    fallback = sum(
        1 for fault in outcome.faults if fault.code is IkFaultCode.UNCONSTRAINED_FALLBACK
    )
    clamps = sum(1 for fault in outcome.faults if fault.code is IkFaultCode.JOINT_LIMIT_CLAMP)

    if outcome.solution_rad is None:
        return RoundTripSample(
            index=index,
            solution_produced=False,
            adapter_held=outcome.held,
            fallback_firings=fallback,
            clamp_firings=clamps,
            residual_right_m=None,
            residual_left_m=None,
            raw_solution_in_limits=None,
        )

    solution = np.asarray(outcome.solution_rad, dtype=float)
    achieved_right, achieved_left = _forward_pose(adapter, solution)
    residual_right = float(
        np.linalg.norm(target_right[:_POSITION_DIM] - achieved_right[:_POSITION_DIM])
    )
    residual_left = float(
        np.linalg.norm(target_left[:_POSITION_DIM] - achieved_left[:_POSITION_DIM])
    )

    return RoundTripSample(
        index=index,
        solution_produced=True,
        adapter_held=outcome.held,
        fallback_firings=fallback,
        clamp_firings=clamps,
        residual_right_m=residual_right,
        residual_left_m=residual_left,
        raw_solution_in_limits=_solution_in_limits(solution, lower, upper),
    )


def run_distribution(
    samples: int = DEFAULT_SAMPLES,
    seed: int = DEFAULT_SEED,
    ik_params: IKParams | None = None,
    allow_unconstrained_fallback: bool = True,
    seed_perturbation_rad: float = 0.0,
    near_limit: bool = False,
) -> RoundTripReport:
    """Run the round-trip harness over N sampled configurations.

    Args:
        samples: Number of configurations to round-trip.
        seed: RNG seed for the sampled configurations.
        ik_params: mink IK parameters; None uses the documented production tuning.
        allow_unconstrained_fallback: Whether IK may fall back to ``limits=[]`` when
            the constrained QP is infeasible. Enabled by default so the harness
            yields a distribution in an environment whose only solver (daqp) reports
            the constrained QP infeasible; every firing is recorded.
        seed_perturbation_rad: Warm-start perturbation std-dev; 0 seeds exactly at q.
        near_limit: When True, draw configurations at the soft-limit boundary
            (acceptance ⑤) rather than the interior.

    Returns:
        (RoundTripReport) The residuals, fault provenance, and a provenance note.
    """
    params = ik_params if ik_params is not None else default_ik_params()
    configs = (
        sample_near_limit_configs(samples, seed)
        if near_limit
        else sample_interior_configs(samples, seed)
    )
    perturb_rng = np.random.default_rng(seed + 1)

    with _quiet_build():
        adapter = build_ik_adapter(
            ik_params=params, allow_unconstrained_fallback=allow_unconstrained_fallback
        )

    results = [
        run_round_trip(adapter, index, config, seed_perturbation_rad, perturb_rng)
        for index, config in enumerate(configs)
    ]

    return RoundTripReport(
        host=platform.node(),
        seed=seed,
        samples=samples,
        allow_unconstrained_fallback=allow_unconstrained_fallback,
        seed_perturbation_rad=seed_perturbation_rad,
        results=results,
        note=_provenance_note(results, allow_unconstrained_fallback),
    )


def _provenance_note(results: list[RoundTripSample], allow_fallback: bool) -> str:
    """Return an honest note on where the residuals came from.

    Args:
        results: The round-trip samples.
        allow_fallback: Whether the unconstrained fallback was enabled.

    Returns:
        (str) A note recording fallback provenance or the constrained-hold state.
    """
    fallback = sum(sample.fallback_firings for sample in results)
    unsolved = sum(1 for sample in results if not sample.solution_produced)
    if allow_fallback and fallback > 0:
        return (
            f"residuals measured through the unconstrained fallback ({fallback} firing(s)): "
            "the only installed QP solver (daqp) reports the constrained ConfigurationLimit "
            "QP infeasible for this model, so a constrained-only run produces no solution "
            "instead. Each firing discards the soft limits (12 FR-SAF-016) and is counted, "
            "not hidden."
        )
    if not allow_fallback and unsolved == len(results) and results:
        return (
            "constrained-only run: every sample produced no solution. In this environment the "
            "daqp constrained QP is infeasible; this is the honest safety-default state, not "
            "a fabricated pass."
        )
    return ""


def format_histogram(residuals: np.ndarray, bins: int = DEFAULT_HISTOGRAM_BINS) -> str:
    """Render an ASCII histogram of an EE-residual distribution.

    Args:
        residuals: Residuals in metres.
        bins: Number of histogram bins.

    Returns:
        (str) A multi-line histogram, or a one-line notice when empty.
    """
    if residuals.size == 0:
        return "(no residuals: every sample held)"

    counts, edges = np.histogram(residuals, bins=bins)
    peak = int(counts.max())
    bar_width = 40
    lines: list[str] = []
    for count, low, high in zip(counts, edges[:-1], edges[1:], strict=True):
        filled = 0 if peak == 0 else round(int(count) * bar_width / peak)
        bar = "#" * filled
        lines.append(f"[{low:.4e}, {high:.4e})  {int(count):>5}  {bar}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the round-trip harness and print the distribution record as JSON.

    Args:
        argv: CLI arguments; None reads ``sys.argv``.

    Returns:
        (int) 0 always — the harness measures, it renders no pass/fail verdict
        (acceptance ⑥).
    """
    parser = argparse.ArgumentParser(
        description="FK<->IK round-trip regression harness (WP-0C-04)."
    )
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES, help="Round trips to run.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Config-sampling RNG seed.")
    parser.add_argument(
        "--near-limit",
        action="store_true",
        help="Sample at the soft-limit boundary instead of the interior.",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable the unconstrained fallback (safety default); may hold every sample.",
    )
    args = parser.parse_args(argv)

    report = run_distribution(
        samples=args.samples,
        seed=args.seed,
        allow_unconstrained_fallback=not args.no_fallback,
        near_limit=args.near_limit,
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
