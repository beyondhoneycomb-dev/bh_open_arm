"""WP-4B-05 — register this band's facts with the Wave 0-Env checker and run them.

`02c` §2.5: this WP adds contract-regression items *through the checker's own API*
and never edits the checker file. The checker exposes two extension points, and both
are used here without touching `registry/env/upstream.py`:

- `run_facts(document)` takes an arbitrary parsed facts document — the data-injection
  point. This band supplies additional facts and hands the merged document to it.
- `PREDICATES` is the module-level resolver table `resolve()` reads live. Additional
  predicates are inserted into it at runtime, so `run_facts` executes them exactly as
  it executes the committed eleven.

Runtime insertion into `PREDICATES` is deliberately not a file edit: the ownership
rule in `02c` §2.5 forbids editing the checker because two waves editing one file
collide in a way worktree isolation cannot resolve. A runtime mutation from this
module touches only this band's files, so no such collision exists. A name that would
shadow a committed predicate is refused rather than silently overwriting it.

The merged document is the base `contracts/upstream_facts.yaml` (Wave 0-Env's eleven,
which already carry items b/d/e and max_state_dim) plus this band's
`contract_regression_facts.yaml`. Together they present all of `FR-OPS-089` (a)–(g)
and the four extra premises in one run, which is `CG-4B-05a`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.compat.contract_regression.predicates import ADDITIONAL_PREDICATES
from registry.env import upstream
from registry.env.upstream import FactResult, FactRow

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_FACTS_PATH = REPO_ROOT / "contracts" / "upstream_facts.yaml"
ADDITIONAL_FACTS_PATH = Path(__file__).resolve().parent / "contract_regression_facts.yaml"


@dataclass(frozen=True)
class RegressionRun:
    """The outcome of one merged contract-regression run.

    Attributes:
        ok: True only when every fact — base and this band's — passed.
        rows: One `FactRow` per fact, in document order, as the checker rendered it.
        registered: The predicate names this band injected into the resolver table.
    """

    ok: bool
    rows: tuple[FactRow, ...]
    registered: tuple[str, ...]

    def failed(self) -> tuple[FactRow, ...]:
        """Return the failed rows, most useful first for a blocked deployment.

        Returns:
            (tuple[FactRow, ...]) The rows whose fact did not hold.
        """
        return tuple(row for row in self.rows if not row.ok)

    def summary(self) -> str:
        """Render a one-line PASS/FAIL summary of the run.

        Returns:
            (str) A line naming the fact count and the failures.
        """
        failed = self.failed()
        if not failed:
            return f"contract regression PASS — {len(self.rows)} facts held"
        names = ", ".join(row.fact_id for row in failed)
        return f"contract regression FAIL — {len(failed)}/{len(self.rows)} facts drifted: {names}"


def register_predicates(
    additional: dict[str, Callable[[], FactResult]] | None = None,
) -> tuple[str, ...]:
    """Inject this band's predicates into the Wave 0-Env resolver table at runtime.

    Idempotent: re-registering the same callable under the same name is a no-op. A
    name already bound to a *different* callable is a collision and is refused —
    shadowing a committed predicate would let this band silently redefine a
    Wave 0-Env fact, which is exactly the cross-wave overwrite the ownership rule
    forbids.

    Args:
        additional: Predicate map to register; defaults to `ADDITIONAL_PREDICATES`.

    Returns:
        (tuple[str, ...]) The predicate names now registered by this band, sorted.

    Raises:
        ValueError: When a name is already bound to a different callable upstream.
    """
    predicates = ADDITIONAL_PREDICATES if additional is None else additional
    for name, predicate in predicates.items():
        existing = upstream.PREDICATES.get(name)
        if existing is not None and existing is not predicate:
            raise ValueError(
                f"predicate {name!r} already bound in registry.env.upstream.PREDICATES; "
                "WP-4B-05 must not shadow a committed Wave 0-Env predicate"
            )
        upstream.PREDICATES[name] = predicate
    return tuple(sorted(predicates))


def merged_facts_document(
    base_path: Path = BASE_FACTS_PATH,
    additional_path: Path = ADDITIONAL_FACTS_PATH,
) -> dict[str, object]:
    """Merge the base Wave 0-Env facts with this band's additional facts.

    Args:
        base_path: Path to `contracts/upstream_facts.yaml`.
        additional_path: Path to this band's `contract_regression_facts.yaml`.

    Returns:
        (dict) A single facts document the checker's `run_facts` can consume.

    Raises:
        ValueError: When a `fact_id` appears in both documents — a duplicate would
            run one item twice and mask which source owns it.
    """
    base = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
    additional = yaml.safe_load(additional_path.read_text(encoding="utf-8")) or {}
    base_facts = list(base.get("facts", []) or [])
    additional_facts = list(additional.get("facts", []) or [])

    seen = {fact.get("fact_id") for fact in base_facts if isinstance(fact, dict)}
    for fact in additional_facts:
        if not isinstance(fact, dict):
            continue
        fact_id = fact.get("fact_id")
        if fact_id in seen:
            raise ValueError(
                f"fact_id {fact_id!r} already declared in {base_path.name}; "
                "WP-4B-05 must not restate a base fact"
            )
        seen.add(fact_id)

    return {"version": base.get("version", 1), "facts": [*base_facts, *additional_facts]}


def run(
    base_path: Path = BASE_FACTS_PATH,
    additional_path: Path = ADDITIONAL_FACTS_PATH,
) -> RegressionRun:
    """Register this band's predicates and run the merged facts through the checker.

    The checker (`registry.env.upstream.run_facts`) does the executing; this function
    only registers and merges, then reads the verdict back.

    Args:
        base_path: Path to `contracts/upstream_facts.yaml`.
        additional_path: Path to this band's additional facts.

    Returns:
        (RegressionRun) The merged verdict — `ok` is False if any fact drifted.
    """
    registered = register_predicates()
    document = merged_facts_document(base_path, additional_path)
    rows = tuple(upstream.run_facts(document))
    return RegressionRun(ok=all(row.ok for row in rows), rows=rows, registered=registered)
