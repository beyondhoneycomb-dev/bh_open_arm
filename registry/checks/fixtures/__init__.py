"""Violation and pass fixtures for every rule in the roster.

`02a` §−2.3 acceptance ② and ③ are the reason this package exists, and `02a` §−2
states the stake plainly: the way this band fails is a checker that catches
nothing while reporting green. A rule with no failing fixture is not implemented,
because nothing has shown it can fail; a rule with no passing fixture may be
over-blocking, which is the same defect wearing the opposite sign.

A fixture is a `Corpus` with substrates injected. `Corpus` caches its substrates
in `cached_property`, so seeding `__dict__` replaces a substrate without touching
the repository — the fixtures are data, and no fixture writes to a path any work
package owns.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from registry.checks.corpus import Corpus, GateCell

REPO_ROOT = Path(__file__).resolve().parents[3]

CLEAN_ENV_HASH = f"sha256:{'0' * 64}"

# A record that satisfies every rule, used as the base every fixture perturbs.
# It cites real ids so that catalogue-, spec- and gate-roster-backed rules resolve.
CLEAN_RECORD: dict[str, Any] = {
    "req": "FR-CAM-001",
    "spec_ref": "06#3.1",
    "priority": "M",
    "tag": "확정",
    "normalization": None,
    "wp": "WP-3A-00",
    "artifact": [{"id": "ART-PRIM", "kind": "schema", "path": "registry/traceability.yaml"}],
    "owns": [],
    "contract": {"consumes": [], "produces": ["CTR-PRIM@v1"]},
    "gate": ["CG-3A-00a"],
    "negative_branch": [
        {"gate": "CG-3A-00a", "on": "FAIL", "action": "redesign the primitive contract"}
    ],
    "downstream": [],
    "terminal": True,
    "stale_on": ["env_hash:CHANGED"],
    "env_hash": CLEAN_ENV_HASH,
    "workflow": "SHAPE-CF",
    "exec_class": "AI-offline",
}


def record(**overrides: Any) -> dict[str, Any]:
    """Build a record from the clean base with fields replaced.

    Args:
        overrides: Field values to replace on the clean record.

    Returns:
        (dict[str, Any]) A registry record.
    """
    built = dict(CLEAN_RECORD)
    built.update(overrides)
    return built


def corpus(
    entries: tuple[dict[str, Any], ...] = (),
    *,
    root: Path | None = None,
    **substrates: Any,
) -> Corpus:
    """Build a fixture corpus with the given records and substrate overrides.

    Args:
        entries: Registry records the fixture presents.
        root: Repository root; defaults to the real one for read-only substrates.
        substrates: Cached properties to seed, such as `tracked_files`.

    Returns:
        (Corpus) A corpus ready to run rules against.
    """
    built = Corpus(
        root or REPO_ROOT,
        plan_dir=REPO_ROOT / "docs" / "plan",
        spec_dir=REPO_ROOT / "docs" / "spec",
    )
    records = tuple(entries) if entries else (record(),)
    built.__dict__["registry"] = {
        "version": 1,
        "spine_ref": f"docs/plan/00-실행계획-개요.md@{'a' * 7}",
        "entries": list(records),
    }
    built.__dict__["entries"] = records
    built.__dict__["spec_requirements"] = frozenset({r["req"] for r in records})
    for name, value in substrates.items():
        built.__dict__[name] = value
    return built


@dataclass(frozen=True)
class FixtureCase:
    """A rule's paired fixtures.

    Attributes:
        rule_id: The rule under test.
        passing: Builds a corpus the rule must accept.
        violating: Builds a corpus the rule must reject.
        note: Why the violating corpus is a violation.
    """

    rule_id: str
    passing: Callable[[Path], Corpus]
    violating: Callable[[Path], Corpus]
    note: str


def _write(root: Path, relative: str, content: str) -> str:
    """Write a file under a fixture root.

    Args:
        root: Fixture root directory.
        relative: Root-relative path.
        content: File content.

    Returns:
        (str) The relative path written.
    """
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative


def _gate_cell(
    value: str, site: str = "registry-gate-axis", path: str = "registry/traceability.yaml"
) -> GateCell:
    """Build a gate declaration site holding a given value.

    Args:
        value: The gate id occupying the site.
        site: Which declaration-site kind to attribute it to.
        path: File the site belongs to. Rules that judge *where* a violation
            sits, rather than only that one exists, need this to vary.

    Returns:
        (GateCell) A declaration site for the trap rules to police.
    """
    return GateCell(value=value, path=path, line=1, site=site, owner="WP-1-04")
