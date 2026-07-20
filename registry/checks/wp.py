"""Work-package views shared by the rules that judge shape, class, and drift.

Three vocabularies live here because more than one rule depends on each, and a
second definition of any of them is how the axes drift apart silently:

* the stage model — a work package is one or many stages, and `06` §5 CI-14/CI-15
  judge *per stage*, never per package;
* the shape-to-class derivation of `00` §4.0;
* the CI-14c field partition, which decides whether two records of the same `wp`
  disagreeing is drift or is normal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from registry.ingest.catalog import ENUM_MARKERS

SHAPE_CF = "SHAPE-CF"
SHAPE_IM = "SHAPE-IM"
SHAPE_IG = "SHAPE-IG"
SHAPE_MS = "SHAPE-MS"
SHAPE_HG = "SHAPE-HG"

# `05` §1.1 owns this vocabulary and it is closed: a sixth shape code is an error,
# not a dialect to translate.
SHAPE_VOCABULARY = frozenset({SHAPE_CF, SHAPE_IM, SHAPE_IG, SHAPE_MS, SHAPE_HG})

EXEC_AI_OFFLINE = "AI-offline"
EXEC_AI_ON_HW = "AI-on-HW"
EXEC_HUMAN_ASSISTED = "Human-assisted-HW"
EXEC_HUMAN_JUDGMENT = "Human-judgment"

EXEC_VOCABULARY = frozenset(
    {EXEC_AI_OFFLINE, EXEC_AI_ON_HW, EXEC_HUMAN_ASSISTED, EXEC_HUMAN_JUDGMENT}
)

# `00` §4.0: exec_class is a function of workflow shape. Only SHAPE-HG splits, and
# it splits because the two classes carry different cancel policies.
SHAPE_TO_EXEC: dict[str, frozenset[str]] = {
    SHAPE_CF: frozenset({EXEC_AI_OFFLINE}),
    SHAPE_IM: frozenset({EXEC_AI_OFFLINE}),
    SHAPE_IG: frozenset({EXEC_AI_OFFLINE}),
    SHAPE_MS: frozenset({EXEC_AI_ON_HW}),
    SHAPE_HG: frozenset({EXEC_HUMAN_ASSISTED, EXEC_HUMAN_JUDGMENT}),
}

CANCEL_POLICIES = frozenset({"finish-step", "latch-to-hold"})

# `06` §5 CI-14c partition (A): these belong to the work package, so every record
# keyed by a requirement under the same `wp` must carry identical values.
WP_IDENTICAL_FIELDS = (
    "workflow",
    "exec_class",
    "phases",
    "owns",
    "gate",
    "negative_branch",
    "stale_on",
    "downstream",
    "targets",
    "terminal",
    "env_hash",
)

WP_IDENTICAL_CONTRACT_FIELDS = ("produces",)

# Partition (B): unique per requirement, so difference is the normal case.
REQ_UNIQUE_FIELDS = ("req", "spec_ref", "priority", "tag", "normalization")

# Partition (C): may vary per requirement or per artifact; difference is allowed.
MAY_VARY_FIELDS = ("artifact", "planned", "justification")

GATE_STATE_PASS = "PASS"
GATE_STATE_FAIL = "FAIL"
GATE_STATE_RETRY = "RETRY_WITH_VARIANT"
GATE_STATE_DEGRADED = "DEGRADED_ACCEPTED"
GATE_STATE_FAIL_BLOCKING = "FAIL_BLOCKING"
GATE_STATE_SUPERSEDED = "SUPERSEDED"

# `06` §5 CI-05c: a PG-* gate must design at least one real failure path.
PG_FAILURE_STATES = frozenset({GATE_STATE_RETRY, GATE_STATE_DEGRADED, GATE_STATE_FAIL_BLOCKING})

# `00` §8.0a is canon: CG-* is PASS/FAIL binary. The five-state machine is PG-*
# only, and CI-05e fails the build on any of these appearing against a CG-*.
CG_FORBIDDEN_STATES = frozenset(
    {GATE_STATE_RETRY, GATE_STATE_DEGRADED, GATE_STATE_FAIL_BLOCKING, GATE_STATE_SUPERSEDED}
)

DEPLOY_TARGETS = frozenset({"jetson_nano", "jetson_orin", "rtx_5090", "rtx_a6000"})

# `06` §5 CI-12: the gate whose verdict is rendered per deployment target.
PER_TARGET_GATES = frozenset({"PG-IK-001"})

CONTRACT_ID = re.compile(r"^CTR-[A-Z]+@v\d+$")

# `06` §4.1: thirteen contracts, canon in `01` §6.2. A fourteenth is an artifact.
CONTRACT_NAMESPACE = frozenset(
    {
        "CTR-PRIM",
        "CTR-OWN",
        "CTR-UNIT",
        "CTR-PLUG",
        "CTR-ACT",
        "CTR-ERR",
        "CTR-GW",
        "CTR-CAL",
        "CTR-CAM",
        "CTR-CAP",
        "CTR-TEL",
        "CTR-WS",
        "CTR-REC",
    }
)

_CG_ID = re.compile(r"^CG-(?P<stem>[A-Z0-9]+-[SG]?\d{1,2})(?P<letter>[a-z])$")


@dataclass(frozen=True)
class Stage:
    """One execution stage of a work package.

    A single-stage package yields exactly one `Stage` with `index` None. `06` §5
    CI-14 and CI-15 judge stages, so a multi-stage package whose second stage is
    a measurement must be caught even when its first stage is compliant.

    Attributes:
        index: Position in `phases[]`, or None for a single-stage package.
        workflow: The `SHAPE-*` token governing this stage.
        exec_class: The execution class declared for this stage.
        owns: Ownership globs the stage claims.
        cancel_policy: Cancellation policy, or empty for a single-stage package.
    """

    index: int | None
    workflow: str
    exec_class: str
    owns: tuple[Any, ...]
    cancel_policy: str

    def label(self) -> str:
        """Render the stage position for a report.

        Returns:
            (str) `phases[n]` for a multi-stage package, else `single-stage`.
        """
        return "single-stage" if self.index is None else f"phases[{self.index}]"


def stages(entry: dict[str, Any]) -> tuple[Stage, ...]:
    """Return the execution stages of a registry record.

    `phases[]` and the scalar `workflow`/`exec_class` pair are mutually exclusive
    per `06` §2.2; when both are absent the record has no stage to judge and the
    result is empty rather than a fabricated default.

    Args:
        entry: A registry record.

    Returns:
        (tuple[Stage, ...]) Stages in declared order.
    """
    phases = entry.get("phases")
    if phases:
        return tuple(
            Stage(
                index=index,
                workflow=str(phase.get("workflow", "")),
                exec_class=str(phase.get("exec_class", "")),
                owns=tuple(phase.get("owns", []) or []),
                cancel_policy=str(phase.get("cancel_policy", "")),
            )
            for index, phase in enumerate(phases)
        )
    workflow = entry.get("workflow")
    if not workflow:
        return ()
    return (
        Stage(
            index=None,
            workflow=str(workflow),
            exec_class=str(entry.get("exec_class", "")),
            owns=tuple(entry.get("owns", []) or []),
            cancel_policy="",
        ),
    )


def shape_sequence(entry: dict[str, Any]) -> tuple[str, ...]:
    """Return the shape tokens of a record's stages, in order.

    Args:
        entry: A registry record.

    Returns:
        (tuple[str, ...]) `SHAPE-*` tokens.
    """
    return tuple(stage.workflow for stage in stages(entry))


def collapse_repeats(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Collapse runs of the same token into one.

    A catalogue shape cell holds one token per *distinct* shape the package passes
    through; `05` §1.1 delegates stage count to `phases[]`, so the catalogue has no
    way to say "two consecutive stages of the same shape". Comparing collapsed
    sequences is the only reading under which the catalogue stays canonical
    without forcing it to encode a stage count it does not own.

    Args:
        tokens: Token sequence.

    Returns:
        (tuple[str, ...]) Sequence with consecutive duplicates removed.
    """
    collapsed: list[str] = []
    for token in tokens:
        if not collapsed or collapsed[-1] != token:
            collapsed.append(token)
    return tuple(collapsed)


def acceptance_count(acceptance_text: str) -> int:
    """Count the enumerated acceptance items in a catalogue acceptance cell.

    `06` §2.4a derives one `CG-*` per acceptance item, so this count is the upper
    bound on the letter suffix a `CG-*` for that package may carry.

    Args:
        acceptance_text: Text of the catalogue acceptance-gate cell.

    Returns:
        (int) Number of enumerated items.
    """
    return sum(1 for char in acceptance_text if char in ENUM_MARKERS)


def derive_cg_id(wp_id: str, ordinal: int) -> str:
    """Derive the acceptance-check id for a package's nth acceptance item.

    Args:
        wp_id: Work-package id such as `WP-3A-00` or `WP-G-S05`.
        ordinal: 1-indexed acceptance item position.

    Returns:
        (str) The derived `CG-*` id.
    """
    return f"CG-{wp_id.removeprefix('WP-')}{chr(ord('a') + ordinal - 1)}"


def parse_cg_id(gate_id: str) -> tuple[str, int] | None:
    """Split a `CG-*` id into the package it derives from and its item ordinal.

    Args:
        gate_id: Candidate acceptance-check id.

    Returns:
        (tuple[str, int] | None) `(WP-*, ordinal)`, or None if malformed.
    """
    match = _CG_ID.match(gate_id)
    if not match:
        return None
    ordinal = ord(match.group("letter")) - ord("a") + 1
    return f"WP-{match.group('stem')}", ordinal


def canonical(value: Any) -> str:
    """Render a field value as a stable string for equality comparison.

    Args:
        value: Any JSON-compatible field value.

    Returns:
        (str) Deterministic serialisation.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
