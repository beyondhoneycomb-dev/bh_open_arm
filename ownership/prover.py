"""The overlap checker and fan-out width prover for CTR-OWN@v1.

`SHAPE-IM` fan-out width `n` was assumed to be 1 until this module could prove
otherwise (`00` §0.3). The proof is an overlap argument: `n` distinct work
packages may run in parallel only when their exclusive ownership globs expand to
disjoint file sets *at the same time*. This module computes that.

Two truths are joined, and neither is copied here — a second copy is a thing that
drifts (`00` §5, working discipline):

- *who owns what* comes from the registry `owns[]` axis
  (`registry/traceability.yaml`), read through the shared `Corpus`. This module
  never restates the glob-to-owner map.
- *when* — the handover order that turns co-ownership into a sequence — comes
  from the `소유 WP` column of `06` §3.2, the same column `CI-02` reads to excuse
  a sequential handover. This module reads it *ordered*, because a span needs a
  direction that an unordered set cannot supply.

The span model itself lives in `ownership.model`; this module assigns spans from
the handover order and then reduces the whole thing to three questions: which
pairs conflict (overlap checker), how wide a cohort may fan out (width prover),
and which produced paths no glob claims (coverage).
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from ownership.model import SPAN_ORIGIN, SPAN_UNIT, Claim, Conflict, Span
from registry.checks.corpus import Corpus
from registry.checks.globs import expand, matches_any, split_globs
from registry.ingest.catalog import WP_ID
from registry.ingest.markdown import all_tables, plain_text

# Modes that forbid concurrent ownership. `EXCLUSIVE` is the plain case;
# `CONTRACT_FROZEN` is single-writer until it freezes and read-only after, so it
# too may never have two live owners. `SHARED_APPEND` and `GENERATED` permit
# concurrency by design and are not exclusive here (`06` §3.1).
EXCLUSIVE_MODES = frozenset({"EXCLUSIVE", "CONTRACT_FROZEN"})

OWNERSHIP_DOC = "06-추적성-레지스트리.md"
OWNER_COLUMN = "소유 WP"

# Until overlap-0 is proven for a cohort, the width degrades to a single serial
# worker (`00` §0.3: degrade to n=1 before a proof exists). A cohort with any
# concurrent conflict has not been proven, so it degrades to this.
DEGRADED_FAN_OUT_WIDTH = 1


def _all_owns(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the package-level and stage-level ownership entries of a record.

    Multi-stage packages can claim a path in `phases[].owns` that the
    package-level `owns[]` union does not spell out, so both are collected — the
    same expansion `CI-02` performs.

    Args:
        record: A registry record.

    Returns:
        (list[dict[str, Any]]) Ownership entries from `owns[]` and `phases[].owns`.
    """
    owned = list(record.get("owns", []) or [])
    for phase in record.get("phases", []) or []:
        owned.extend(phase.get("owns", []) or [])
    return owned


def exclusive_owners(corpus: Corpus) -> dict[str, tuple[str, ...]]:
    """Map each exclusively-owned glob to the packages that claim it.

    Args:
        corpus: The corpus whose registry supplies the ownership truth.

    Returns:
        (dict[str, tuple[str, ...]]) Glob to its owning `WP-*`s, sorted. A glob
        with two owners is either a declared handover or a conflict; which one is
        decided later against the handover order.
    """
    owners: dict[str, set[str]] = defaultdict(set)
    for wp_id, records in corpus.by_wp.items():
        for record in records:
            for owned in _all_owns(record):
                if owned.get("mode") not in EXCLUSIVE_MODES:
                    continue
                for glob in split_globs(str(owned.get("glob", ""))):
                    owners[glob].add(wp_id)
    return {glob: tuple(sorted(wps)) for glob, wps in owners.items()}


def owned_globs(corpus: Corpus) -> tuple[str, ...]:
    """Collect every ownership glob in the registry, regardless of mode.

    Coverage is a question about ownership of any kind, so this is the union over
    all modes — not only the exclusive ones the conflict check looks at.

    Args:
        corpus: The corpus whose registry supplies the ownership truth.

    Returns:
        (tuple[str, ...]) Every declared glob, sorted and de-duplicated.
    """
    globs: set[str] = set()
    for record in corpus.entries:
        for owned in _all_owns(record):
            globs.update(split_globs(str(owned.get("glob", ""))))
    return tuple(sorted(globs))


def read_handover_chains(plan_dir: Path) -> tuple[tuple[str, ...], ...]:
    """Read the ordered handover chains from the `소유 WP` column of `06` §3.2.

    `CI-02` reads this same column as an unordered set, because it only needs to
    know that a handover was declared. A span needs the direction, so this reader
    preserves source order: `WP-1-02 → WP-1-03` yields `(WP-1-02, WP-1-03)`, and
    the arrow's left-to-right reading is the succession order the spans encode.

    Args:
        plan_dir: Directory holding the planning documents.

    Returns:
        (tuple[tuple[str, ...], ...]) One ordered tuple per multi-owner row.
    """
    path = plan_dir / OWNERSHIP_DOC
    if not path.is_file():
        return ()
    chains: list[tuple[str, ...]] = []
    for table in all_tables(path):
        owner_column = table.exact_column_index(OWNER_COLUMN)
        if owner_column is None:
            continue
        for row in table.rows:
            if owner_column >= len(row):
                continue
            packages = tuple(dict.fromkeys(WP_ID.findall(plain_text(row[owner_column]))))
            if len(packages) > 1:
                chains.append(packages)
    return tuple(chains)


def _spans_for_glob(
    owners: tuple[str, ...], chains: tuple[tuple[str, ...], ...]
) -> dict[str, Span]:
    """Assign a span to each owner of one glob from the handover order.

    A single owner holds the whole timeline, `[0, 1)`. When several packages own
    the glob and a declared chain contains all of them, they are laid end to end
    in chain order — package at chain position `i` owns `[i, i+1)` — so adjacent
    owners never overlap. When no chain contains them, they all claim the origin
    interval and therefore collide, which is exactly the concurrent-ownership
    fault the checker must surface.

    Args:
        owners: The packages that own the glob.
        chains: The declared ordered handover chains.

    Returns:
        (dict[str, Span]) Owner to the span it holds the glob for.
    """
    owner_set = set(owners)
    for chain in chains:
        if owner_set <= set(chain):
            ordered = [wp for wp in chain if wp in owner_set]
            return {
                wp: Span(SPAN_ORIGIN + index * SPAN_UNIT, SPAN_ORIGIN + (index + 1) * SPAN_UNIT)
                for index, wp in enumerate(ordered)
            }
    # One shared frozen Span for every concurrent owner: identical [0, 1) intervals
    # is exactly what makes them overlap, and Span is immutable so sharing is safe.
    unit = Span(SPAN_ORIGIN, SPAN_ORIGIN + SPAN_UNIT)
    return dict.fromkeys(owners, unit)


def assemble_claims(
    owners_by_glob: dict[str, tuple[str, ...]], chains: tuple[tuple[str, ...], ...]
) -> tuple[Claim, ...]:
    """Build the CTR-OWN@v1 claim view from the ownership map and handover order.

    Args:
        owners_by_glob: Exclusive glob to its owning packages
            (`exclusive_owners`).
        chains: The declared ordered handover chains (`read_handover_chains`).

    Returns:
        (tuple[Claim, ...]) One claim per (glob, owner), each carrying its span.
    """
    claims: list[Claim] = []
    for glob in sorted(owners_by_glob):
        owners = owners_by_glob[glob]
        spans = _spans_for_glob(owners, chains)
        for wp_id in owners:
            claims.append(Claim(path_glob=glob, owner_wp=wp_id, exclusive=True, span=spans[wp_id]))
    return tuple(claims)


def concurrent_conflicts(claims: tuple[Claim, ...], files: tuple[str, ...]) -> tuple[Conflict, ...]:
    """Report pairs of exclusive claims that own one real file at one time.

    A pair conflicts when both claims are exclusive, they belong to different
    packages, their spans overlap, and their globs expand to a common real file.
    All four are required: the span test alone would reject a lawful handover,
    and the glob test alone would reject two packages that share a span but no
    file (`CI-02` expands to real files for the same reason).

    Args:
        claims: The CTR-OWN@v1 claim view.
        files: Root-relative POSIX paths the globs expand against.

    Returns:
        (tuple[Conflict, ...]) One conflict per overlapping pair, in a stable
        order.
    """
    expansions = {claim.path_glob: expand((claim.path_glob,), files) for claim in claims}
    conflicts: list[Conflict] = []
    for left, right in combinations(claims, 2):
        if left.owner_wp == right.owner_wp:
            continue
        if not (left.exclusive and right.exclusive):
            continue
        if not left.span.overlaps(right.span):
            continue
        shared = expansions[left.path_glob] & expansions[right.path_glob]
        if not shared:
            continue
        first, second = sorted((left.owner_wp, right.owner_wp))
        conflicts.append(
            Conflict(
                left_wp=first,
                right_wp=second,
                left_glob=left.path_glob,
                right_glob=right.path_glob,
                shared_paths=tuple(sorted(shared)),
            )
        )
    return tuple(conflicts)


def fan_out_width(
    cohort: tuple[str, ...], claims: tuple[Claim, ...], files: tuple[str, ...]
) -> int:
    """Compute the proven fan-out width of a cohort of work packages.

    The width is the count of distinct packages in the cohort once overlap-0 is
    proven among them. If any two cohort members concurrently own a shared file,
    the cohort is not overlap-0 and the width degrades to a single serial worker
    — the `n=1` fallback `00` §0.3 mandates before a proof exists.

    Args:
        cohort: The work packages that would fan out in parallel.
        claims: The CTR-OWN@v1 claim view.
        files: Root-relative POSIX paths the globs expand against.

    Returns:
        (int) The distinct cohort size when overlap-free, else the degraded
        width `1`.
    """
    members = set(cohort)
    cohort_claims = tuple(claim for claim in claims if claim.owner_wp in members)
    if concurrent_conflicts(cohort_claims, files):
        return DEGRADED_FAN_OUT_WIDTH
    return len(members)


def unowned_paths(paths: tuple[str, ...], globs: tuple[str, ...]) -> tuple[str, ...]:
    """Return the paths that no ownership glob claims.

    This answers both the coverage question — a produced file no glob owns is an
    accountability hole — and the unowned-edit question — an edit to a path no
    glob owns has no owner to attribute it to. Both reduce to "is this path
    matched by any declared glob".

    Args:
        paths: Root-relative POSIX paths to test.
        globs: The declared ownership globs (`owned_globs`).

    Returns:
        (tuple[str, ...]) The subset of `paths` matched by no glob, in order.
    """
    return tuple(path for path in paths if not matches_any(path, globs))
