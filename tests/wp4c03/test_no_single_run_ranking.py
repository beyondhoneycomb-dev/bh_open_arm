"""CG-4C-03e — there is no code path that ranks two checkpoints from a single run.

`FR-INF-063`: nondeterministic augmentation alone swings success 5-6%p, so a single
execution's ordering is noise. This test is both behavioural (single-run inputs
never rank) and static (the only function that can emit an ordered verdict is the
guarded `compare_checkpoints`, and it takes sequences, not single reports). A
positive control proves the guard does not simply block everything.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from backend.eval.stats import (
    MIN_INDEPENDENT_RUNS,
    VERDICT_A_BETTER,
    VERDICT_B_BETTER,
    VERDICT_UNDETERMINED,
    aggregator,
    compare_checkpoints,
)
from backend.eval.stats.constants import REASON_SINGLE_RUN
from tests.wp4c03.support import report

_STATS_PACKAGE_DIR = Path(inspect.getfile(aggregator)).parent
_ORDERED_VERDICTS = {"VERDICT_A_BETTER", "VERDICT_B_BETTER"}


def test_single_run_each_side_is_undetermined() -> None:
    """One run per side -> UNDETERMINED / single-run, never an ordering."""
    result = compare_checkpoints(
        [report(20, 20, "/runs/a")],
        [report(0, 20, "/runs/b")],
    )
    assert result.verdict == VERDICT_UNDETERMINED
    assert result.reason == REASON_SINGLE_RUN
    assert result.is_ranked is False


def test_one_side_single_run_is_undetermined() -> None:
    """Even a lopsided count (1 vs 2) is refused — every side needs >=2 runs."""
    result = compare_checkpoints(
        [report(20, 20, "/runs/a")],
        [report(0, 20, "/runs/b"), report(0, 20, "/runs/b")],
    )
    assert result.verdict == VERDICT_UNDETERMINED
    assert result.reason == REASON_SINGLE_RUN


def test_no_single_run_pair_ever_ranks() -> None:
    """Across a spread of single-run outcomes, no single-run pair produces a ranking."""
    for success_a in (0, 5, 10, 20):
        for success_b in (0, 5, 10, 20):
            result = compare_checkpoints(
                [report(success_a, 20, "/runs/a")],
                [report(success_b, 20, "/runs/b")],
            )
            assert result.is_ranked is False


def test_minimum_independent_runs_is_at_least_two() -> None:
    """The floor is 'not single', i.e. >=2 — the requirement's own implied minimum."""
    assert MIN_INDEPENDENT_RUNS >= 2


def test_positive_control_disjoint_cis_do_rank() -> None:
    """With >=2 meaningful runs per side and disjoint CIs, ranking IS produced.

    Guards must discriminate, not block everything: an all-success checkpoint must
    beat an all-failure one, or CG-4C-03e would be satisfied by a constant stub.
    """
    result = compare_checkpoints(
        [report(20, 20, "/runs/a"), report(20, 20, "/runs/a")],
        [report(0, 20, "/runs/b"), report(0, 20, "/runs/b")],
    )
    assert result.verdict == VERDICT_A_BETTER
    assert result.is_ranked is True


def test_overlapping_cis_do_not_rank() -> None:
    """Two near-identical checkpoints (overlapping Wilson CIs) return UNDETERMINED."""
    result = compare_checkpoints(
        [report(10, 20, "/runs/a"), report(11, 20, "/runs/a")],
        [report(10, 20, "/runs/b"), report(9, 20, "/runs/b")],
    )
    assert result.verdict == VERDICT_UNDETERMINED
    assert result.is_ranked is False


def _constructs_ordered_verdict(function: ast.FunctionDef) -> bool:
    """Whether a function builds a `CheckpointComparison` with an ordered verdict.

    This is emission, not mere reference: it looks for a `CheckpointComparison(...)`
    call whose `verdict` argument resolves to an ordered verdict name. A predicate
    that only reads the verdict (like `is_ranked`'s membership test) constructs no
    comparison and is correctly not counted.
    """
    for call in ast.walk(function):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
            continue
        if call.func.id != "CheckpointComparison":
            continue
        for keyword in call.keywords:
            if keyword.arg != "verdict":
                continue
            names = {n.id for n in ast.walk(keyword.value) if isinstance(n, ast.Name)}
            if names & _ORDERED_VERDICTS:
                return True
    return False


def test_static_only_compare_checkpoints_emits_an_ordered_verdict() -> None:
    """Static check: no function outside `compare_checkpoints` can emit an ordering.

    Any ordered verdict must be constructed inside the guarded comparison, so
    scanning the package's sources for functions that build a `CheckpointComparison`
    with an ordered verdict must find exactly one: `compare_checkpoints`.
    """
    emitting: set[str] = set()
    for source_path in _STATS_PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and _constructs_ordered_verdict(node):
                emitting.add(node.name)
    assert emitting == {"compare_checkpoints"}, (
        f"only compare_checkpoints may emit an ordered verdict; found {sorted(emitting)}"
    )


def test_static_compare_checkpoints_takes_sequences_not_single_reports() -> None:
    """Static check: the comparison API takes sequences of runs, not single reports."""
    signature = inspect.signature(compare_checkpoints)
    assert list(signature.parameters) == ["runs_a", "runs_b"]
    for name in ("runs_a", "runs_b"):
        annotation = str(signature.parameters[name].annotation)
        assert "Sequence" in annotation, f"{name} must be a Sequence of runs, got {annotation}"


def test_ordered_verdict_values_are_distinct() -> None:
    """Sanity: the three verdicts are distinct string values."""
    assert len({VERDICT_A_BETTER, VERDICT_B_BETTER, VERDICT_UNDETERMINED}) == 3
