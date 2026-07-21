"""The paired fixture corpora, one entry per rule in the roster.

Each case names what makes its violating corpus a violation, so a reader can tell
whether the fixture exercises the rule's actual predicate or merely something
adjacent to it. A fixture that fails for an unrelated reason proves nothing about
the rule it is filed under.
"""

from __future__ import annotations

import json
from pathlib import Path

from registry.checks.corpus import Corpus
from registry.checks.fixtures import (
    REPO_ROOT,
    FixtureCase,
    _gate_cell,
    _write,
    corpus,
    record,
)

CLEAN_TREE = ("registry/traceability.yaml",)


def _tree(root: Path, *paths: str) -> tuple[str, ...]:
    """Materialise files under a fixture root and return their paths.

    Args:
        root: Fixture root directory.
        paths: Root-relative paths to create with placeholder content.

    Returns:
        (tuple[str, ...]) The created paths.
    """
    return tuple(_write(root, path, "placeholder\n") for path in paths)


# --- CI-01 / CI-01b -------------------------------------------------------


def _ci01_pass(_root: Path) -> Corpus:
    return corpus()


def _ci01_violation(_root: Path) -> Corpus:
    built = corpus()
    built.__dict__["spec_requirements"] = frozenset({"FR-CAM-001", "FR-CAM-999"})
    return built


def _ci01b_pass(_root: Path) -> Corpus:
    return corpus()


def _ci01b_violation(_root: Path) -> Corpus:
    built = corpus((record(req="FR-ZZZ-404"),))
    built.__dict__["spec_requirements"] = frozenset({"FR-CAM-001"})
    return built


# --- CI-02 / CI-02b -------------------------------------------------------

_SHARED_FILE = "backend/actuation/scheduler.py"


def _ci02_pass(root: Path) -> Corpus:
    tree = _tree(root, _SHARED_FILE)
    entries = (
        record(wp="WP-0A-01", owns=[{"glob": "backend/actuation/**", "mode": "EXCLUSIVE"}]),
        record(wp="WP-1-03", owns=[{"glob": "backend/actuation/**", "mode": "EXCLUSIVE"}]),
    )
    return corpus(entries, root=root, tracked_files=tree)


def _ci02_violation(root: Path) -> Corpus:
    tree = _tree(root, _SHARED_FILE)
    entries = (
        record(wp="WP-0A-01", owns=[{"glob": "backend/actuation/**", "mode": "EXCLUSIVE"}]),
        record(wp="WP-5-01", owns=[{"glob": "backend/actuation/**", "mode": "EXCLUSIVE"}]),
    )
    return corpus(entries, root=root, tracked_files=tree)


def _ci02b_pass(root: Path) -> Corpus:
    entries = (record(owns=[{"glob": "backend/actuation/**", "mode": "EXCLUSIVE"}]),)
    return corpus(entries, root=root, artifact_tree=("backend/actuation/scheduler.py",))


def _ci02b_violation(root: Path) -> Corpus:
    entries = (record(owns=[{"glob": "backend/actuation/**", "mode": "EXCLUSIVE"}]),)
    return corpus(entries, root=root, artifact_tree=("web/screens/S-01/App.tsx",))


# --- CI-03 family ---------------------------------------------------------


def _ci03_pass(_root: Path) -> Corpus:
    return corpus()


def _ci03_violation(_root: Path) -> Corpus:
    return corpus(
        (
            record(wp="WP-3A-00", contract={"consumes": [], "produces": ["CTR-PRIM@v1"]}),
            record(wp="WP-0A-02", contract={"consumes": [], "produces": ["CTR-PRIM@v1"]}),
        )
    )


_OA_CODES = "contracts/errors/oa_codes.yaml"


def _ci03b_pass(root: Path) -> Corpus:
    _write(
        root,
        _OA_CODES,
        "codes:\n  - code: OA-CAN-001\n    wp: WP-0B-01\n  - code: OA-CAN-002\n    wp: WP-0B-01\n",
    )
    return corpus(root=root)


def _ci03b_violation(root: Path) -> Corpus:
    _write(
        root,
        _OA_CODES,
        "codes:\n  - code: OA-DAT-003\n    wp: WP-OPS-06\n  - code: OA-DAT-003\n    wp: WP-4A-01\n",
    )
    return corpus(root=root)


def _ci03c_pass(_root: Path) -> Corpus:
    return corpus()


def _ci03c_violation(_root: Path) -> Corpus:
    return corpus(
        (record(contract={"consumes": ["CT-RT-BUDGET@v1"], "produces": ["CTR-PRIM@v1"]}),)
    )


def _primitive_consumers(stale_on: list[str]) -> tuple[dict[str, object], ...]:
    return tuple(
        record(
            wp=f"WP-3A-0{index}",
            contract={"consumes": ["CTR-PRIM@v1"], "produces": []},
            stale_on=stale_on,
            gate=[f"CG-3A-0{index}a"],
            negative_branch=[{"gate": f"CG-3A-0{index}a", "on": "FAIL", "action": "redesign"}],
        )
        for index in range(1, 6)
    )


def _ci03d_pass(_root: Path) -> Corpus:
    return corpus(_primitive_consumers(["CTR-PRIM:MAJOR_BUMP"]))


def _ci03d_violation(_root: Path) -> Corpus:
    return corpus(_primitive_consumers(["env_hash:CHANGED"]))


# --- CI-04 family ---------------------------------------------------------


def _ci04_pass(_root: Path) -> Corpus:
    return corpus()


def _ci04_violation(_root: Path) -> Corpus:
    return corpus((record(gate=[], negative_branch=[]),))


def _ci04_deferred_exempt(_root: Path) -> Corpus:
    """A DEFERRED record with no gate must stay green — the exemption fixture."""
    return corpus((record(wp="DEFERRED", gate=[], negative_branch=[]),))


def _ci04b_pass(_root: Path) -> Corpus:
    return corpus()


def _ci04b_violation(_root: Path) -> Corpus:
    return corpus((record(artifact=[]),))


def _ci04c_pass(_root: Path) -> Corpus:
    return corpus()


def _ci04c_violation(_root: Path) -> Corpus:
    return corpus(
        (
            record(
                gate=["CG-3A-00z"],
                negative_branch=[{"gate": "CG-3A-00z", "on": "FAIL", "action": "redesign"}],
            ),
        )
    )


def _ci04d_pass(_root: Path) -> Corpus:
    return corpus((record(wp="OUT", out_reason="U-1 bilateral ruled physically impossible"),))


def _ci04d_violation(_root: Path) -> Corpus:
    return corpus((record(wp="OUT", out_reason="not doing it"),))


# --- CI-05 family ---------------------------------------------------------


def _ci05_pass(_root: Path) -> Corpus:
    return corpus()


def _ci05_violation(_root: Path) -> Corpus:
    return corpus((record(negative_branch=[]),))


_SPAWN_GATE = {"gate": "CG-3A-00a", "on": "FAIL", "action": "respawn"}


def _ci05b_pass(_root: Path) -> Corpus:
    return corpus((record(negative_branch=[{**_SPAWN_GATE, "spawns": "WP-0C-02"}]),))


def _ci05b_violation(_root: Path) -> Corpus:
    return corpus((record(negative_branch=[{**_SPAWN_GATE, "spawns": "WP-NOPE-99"}]),))


def _pg_record(states: list[str]) -> dict[str, object]:
    return record(
        wp="WP-1-04",
        gate=["PG-RT-001a", "PG-RT-001b"],
        stale_on=["PG-RT-001b:PASS"],
        negative_branch=[
            {"gate": "PG-RT-001a", "on": state, "action": "split the worker"} for state in states
        ]
        + [{"gate": "PG-RT-001b", "on": "FAIL_BLOCKING", "action": "halt"}],
    )


def _ci05c_pass(_root: Path) -> Corpus:
    return corpus((_pg_record(["RETRY_WITH_VARIANT"]),))


def _ci05c_violation(_root: Path) -> Corpus:
    return corpus((_pg_record(["PASS", "SUPERSEDED"]),))


def _ci05d_pass(_root: Path) -> Corpus:
    return corpus((record(negative_branch=[{**_SPAWN_GATE, "spawns": "WP-0C-02"}]),))


def _ci05d_violation(_root: Path) -> Corpus:
    return corpus((record(negative_branch=[{**_SPAWN_GATE, "spawns": "WP-3A-00R"}]),))


def _ci05e_pass(_root: Path) -> Corpus:
    return corpus()


def _ci05e_violation(_root: Path) -> Corpus:
    return corpus(
        (
            record(
                negative_branch=[
                    {"gate": "CG-3A-00a", "on": "DEGRADED_ACCEPTED", "action": "accept reduced"}
                ]
            ),
        )
    )


# --- CI-06 / CI-07 / CI-08 / CI-09 ---------------------------------------


def _ci06_pass(root: Path) -> Corpus:
    return corpus(
        (
            record(
                artifact=[{"id": "ART-X", "kind": "report", "path": "not/built.json"}], planned=True
            ),
        ),
        root=root,
    )


def _ci06_violation(root: Path) -> Corpus:
    return corpus(
        (record(artifact=[{"id": "ART-X", "kind": "report", "path": "not/built.json"}]),),
        root=root,
    )


_CONTESTED_REQ = "FR-CON-061"


def _ci07_pass(_root: Path) -> Corpus:
    return corpus((record(req=_CONTESTED_REQ, normalization=f"sha256:{'b' * 64}"),))


def _ci07_violation(_root: Path) -> Corpus:
    return corpus((record(req=_CONTESTED_REQ, normalization=None),))


def _ci07_deferred_exempt(_root: Path) -> Corpus:
    """A DEFERRED record needs no ledger hash — the exemption fixture."""
    return corpus((record(req=_CONTESTED_REQ, wp="DEFERRED", normalization=None),))


def _ci08_pass(_root: Path) -> Corpus:
    return corpus((record(contract={"consumes": ["CTR-ACT@v1"], "produces": []}),))


def _ci08_violation(_root: Path) -> Corpus:
    return corpus((record(contract={"consumes": ["CTR-ACT@^v1"], "produces": []}),))


_FROZEN_GLOB = "contracts/unit_tags.yaml"


def _ci09_corpus(root: Path, registered_hash: str | None) -> Corpus:
    _write(root, _FROZEN_GLOB, "Deg: rad\n")
    # The freeze authority (`registry/contracts/`, WP-BOOT-05), not the BOOT-02
    # build index: `contracts[]` is a list and a lock is a FROZEN row carrying a
    # `canonical_hash`.
    contracts = (
        [{"contract_id": "CTR-UNIT@v1", "canonical_hash": registered_hash, "status": "FROZEN"}]
        if registered_hash
        else []
    )
    _write(root, "registry/contracts/contract_index.json", json.dumps({"contracts": contracts}))
    entries = (
        record(
            wp="WP-0A-04",
            contract={"consumes": [], "produces": ["CTR-UNIT@v1"]},
            owns=[{"glob": _FROZEN_GLOB, "mode": "CONTRACT_FROZEN"}],
        ),
    )
    return corpus(entries, root=root, tracked_files=(_FROZEN_GLOB,))


def _ci09_pass(root: Path) -> Corpus:
    from registry.checks.ci_09 import content_hash

    _write(root, _FROZEN_GLOB, "Deg: rad\n")
    return _ci09_corpus(root, content_hash((_FROZEN_GLOB,), root))


def _ci09_violation(root: Path) -> Corpus:
    return _ci09_corpus(root, f"sha256:{'e' * 64}")


# --- CI-10 / CI-11 family -------------------------------------------------


def _ci10_pass(_root: Path) -> Corpus:
    return corpus(gate_declaration_sites=(_gate_cell("PG-RT-001a"),))


def _ci10_violation(_root: Path) -> Corpus:
    return corpus(
        gate_declaration_sites=(
            _gate_cell("M-8", site="manifest-gates"),
            _gate_cell("M-8", site="gate-table-id-cell"),
        )
    )


def _ci11b_pass(_root: Path) -> Corpus:
    return corpus(gate_declaration_sites=(_gate_cell("PG-RT-001a"), _gate_cell("PG-RT-001b")))


def _ci11b_violation(_root: Path) -> Corpus:
    return corpus(
        gate_declaration_sites=(
            _gate_cell("PG-RT-001", site="manifest-gates"),
            _gate_cell("PG-RT-001", site="registry-gate-axis"),
        )
    )


_ANCHORED_SOURCE = "backend/rt/budget.py"


def _ci11_corpus(root: Path, body: str) -> Corpus:
    _write(root, _ANCHORED_SOURCE, body)
    entries = (
        record(
            wp="WP-1-04",
            gate=["PG-RT-001a"],
            stale_on=["PG-RT-001b:PASS"],
            negative_branch=[{"gate": "PG-RT-001a", "on": "RETRY_WITH_VARIANT", "action": "retry"}],
            owns=[{"glob": _ANCHORED_SOURCE, "mode": "EXCLUSIVE"}],
        ),
    )
    return corpus(entries, root=root, tracked_files=(_ANCHORED_SOURCE,))


_ANCHORED_EVIDENCE = "registry/build/evidence/PG-RT-001a/hash.json"

# Every shape CI-11 must tolerate in one file: an annotated constant that cites its
# evidence, a tuple whose *values* are the annotation tokens, a docstring that
# explains the rule, and a constant carrying no annotation at all. Only the first is
# a site, and the middle two are the shapes a file-granularity checker mistook for
# one.
_CI11_PASS_SOURCE = f'''"""Control-loop budget.

Constants here carry an @target annotation naming the run that measured them.
"""

ANNOTATION_TOKENS = ("@target", "@threshold")

RETRY_LIMIT = 3

# @target f_max, measured by {_ANCHORED_EVIDENCE}
F_MAX_HZ = 250
'''

# One correctly anchored declaration above one that cites nothing. A checker asking
# whether the *file* mentions an evidence path calls this clean, which is the false
# negative that made CI-11 judge the wrong unit.
_CI11_VIOLATION_SOURCE = f"""# @target f_max, measured by {_ANCHORED_EVIDENCE}
F_MAX_HZ = 250

# @threshold end-to-end latency budget
LATENCY_BUDGET_MS = 12
"""

# The declaration the violating fixture must be reported against, named here so the
# assertion and the fixture cannot drift apart.
CI11_UNANCHORED_NAME = "LATENCY_BUDGET_MS"
CI11_UNANCHORED_LINE = 5

_CI11_MENTIONS_ONLY_SOURCE = '''"""This module explains the @target annotation.

It declares no target of its own.
"""

ANNOTATION_TOKENS = ("@target", "@threshold")

RETRY_LIMIT = 3
'''

_CI11_LONE_VIOLATION_SOURCE = "# @target control loop budget\nF_MAX_HZ = 250\n"


def _ci11_pass(root: Path) -> Corpus:
    return _ci11_corpus(root, _CI11_PASS_SOURCE)


def _ci11_violation(root: Path) -> Corpus:
    return _ci11_corpus(root, _CI11_VIOLATION_SOURCE)


def _ci11_mentions_only(root: Path) -> Corpus:
    return _ci11_corpus(root, _CI11_MENTIONS_ONLY_SOURCE)


def _ci11_lone_violation(root: Path) -> Corpus:
    return _ci11_corpus(root, _CI11_LONE_VIOLATION_SOURCE)


def _ci11b_self_pass(_root: Path) -> Corpus:
    """CI-11b is green on the originals, so the self-application rule is satisfied."""
    return corpus(gate_declaration_sites=(_gate_cell("PG-RT-001a"),))


def _ci11b_self_violation(_root: Path) -> Corpus:
    """A canonical planning document carries the undivided id at a declaration site.

    Condition 3 fails: CI-11b is not green on the corpus as it stands, so either the
    document holds a real violation or the checker over-blocks its own rationale.
    Both readings must stop the build; neither may pass silently.
    """
    return corpus(
        gate_declaration_sites=(
            _gate_cell(
                "PG-RT-001",
                site="registry-gate-axis",
                path="docs/plan/00-실행계획-개요.md",
            ),
        )
    )


def _ci11c_pass(_root: Path) -> Corpus:
    return corpus(
        (
            record(
                wp="WP-1-04",
                gate=["PG-RT-001a"],
                stale_on=["PG-RT-001b:PASS"],
                negative_branch=[{"gate": "PG-RT-001a", "on": "RETRY_WITH_VARIANT", "action": "x"}],
            ),
        )
    )


def _ci11c_violation(_root: Path) -> Corpus:
    return corpus(
        (
            record(
                wp="WP-1-04",
                gate=["PG-RT-001a"],
                stale_on=["env_hash:CHANGED"],
                negative_branch=[{"gate": "PG-RT-001a", "on": "RETRY_WITH_VARIANT", "action": "x"}],
            ),
        )
    )


_ALL_TARGETS = ["jetson_nano", "jetson_orin", "rtx_5090", "rtx_a6000"]


def _ci12_record(targets: list[str]) -> dict[str, object]:
    return record(
        wp="WP-3C-01",
        gate=["PG-IK-001"],
        targets=targets,
        negative_branch=[
            {"gate": "PG-IK-001", "on": "DEGRADED_ACCEPTED", "action": "mark unsupported"}
        ],
    )


def _ci12_pass(_root: Path) -> Corpus:
    return corpus((_ci12_record(_ALL_TARGETS),))


def _ci12_violation(_root: Path) -> Corpus:
    return corpus((_ci12_record(["jetson_nano", "rtx_5090"]),))


# --- CI-14 family / CI-15 -------------------------------------------------


def _ci14_pass(_root: Path) -> Corpus:
    return corpus()


def _ci14_violation(_root: Path) -> Corpus:
    return corpus((record(workflow="SHAPE-CF", exec_class="AI-on-HW"),))


def _ci14_stage_violation(_root: Path) -> Corpus:
    """A compliant first stage must not hide a non-compliant second one."""
    return corpus(
        (
            record(
                workflow=None,
                exec_class=None,
                phases=[
                    {
                        "workflow": "SHAPE-CF",
                        "exec_class": "AI-offline",
                        "owns": [],
                        "cancel_policy": "finish-step",
                        "after": None,
                    },
                    {
                        "workflow": "SHAPE-IM",
                        "exec_class": "AI-on-HW",
                        "owns": [],
                        "cancel_policy": "latch-to-hold",
                        "after": 0,
                    },
                ],
            ),
        )
    )


def _ci14b_pass(_root: Path) -> Corpus:
    return corpus()


def _ci14b_violation(_root: Path) -> Corpus:
    return corpus((record(wp="WP-3A-00", workflow="SHAPE-MS", exec_class="AI-on-HW"),))


def _ci14c_pass(_root: Path) -> Corpus:
    return corpus(
        (
            record(req="FR-CAM-001"),
            record(req="FR-CAM-006"),
        )
    )


def _ci14c_violation(_root: Path) -> Corpus:
    return corpus(
        (
            record(req="FR-CAM-001", downstream=["WP-3B-01"], terminal=None),
            record(req="FR-CAM-006", downstream=["WP-3B-02"], terminal=None),
        )
    )


def _ms_record(owns: list[dict[str, str]]) -> dict[str, object]:
    return record(
        wp="WP-0B-07",
        workflow="SHAPE-MS",
        exec_class="AI-on-HW",
        owns=owns,
        gate=["PG-RID-001"],
        negative_branch=[{"gate": "PG-RID-001", "on": "FAIL_BLOCKING", "action": "halt"}],
    )


def _ci15_pass(_root: Path) -> Corpus:
    return corpus((_ms_record([]),))


def _ci15_violation(_root: Path) -> Corpus:
    return corpus((_ms_record([{"glob": "backend/motors/**", "mode": "EXCLUSIVE"}]),))


# --- CI-16 / CI-17 / CI-18 ------------------------------------------------


def _ci16_corpus(root: Path, justification: str | None) -> Corpus:
    producer = _write(root, "pkg_a/mod.py", "VALUE = 1\n")
    consumer = _write(root, "pkg_b/mod.py", "CONSTANT = 2\n")
    entries = (
        record(
            wp="WP-0A-01",
            owns=[{"glob": "pkg_a/**", "mode": "EXCLUSIVE"}],
            downstream=["WP-1-03"],
            terminal=None,
            justification=justification,
        ),
        record(
            req="FR-CAM-006",
            wp="WP-1-03",
            owns=[{"glob": "pkg_b/**", "mode": "EXCLUSIVE"}],
        ),
    )
    return corpus(entries, root=root, tracked_files=(producer, consumer))


def _ci16_pass(root: Path) -> Corpus:
    return _ci16_corpus(root, "consumed by runtime dynamic load; invisible to a static graph")


def _ci16_violation(root: Path) -> Corpus:
    return _ci16_corpus(root, None)


_SPINE_DOC = REPO_ROOT / "docs" / "plan" / "00-실행계획-개요.md"


def _ci17_pass(_root: Path) -> Corpus:
    # Scoped to the spine document alone: it is what `spine_ref` cites, and its own
    # SPINE citations all resolve, so the fixture isolates the rule from the real
    # corpus's dangling citations in `02a`.
    return corpus(plan_paths=(_SPINE_DOC,))


def _ci17_violation(_root: Path) -> Corpus:
    return corpus((record(spec_ref="06#99.99"),), plan_paths=(_SPINE_DOC,))


def _state_corpus(root: Path, state: str) -> Corpus:
    _write(
        root,
        "registry/state/workflow_state.json",
        f'{{"states": {{"WP-N1-01": "{state}"}}}}',
    )
    return corpus(root=root)


def _ci18_pass(root: Path) -> Corpus:
    return _state_corpus(root, "미착수")


def _ci18_violation(root: Path) -> Corpus:
    return _state_corpus(root, "활성")


CASES: tuple[FixtureCase, ...] = (
    FixtureCase("CI-01", _ci01_pass, _ci01_violation, "a declared requirement no record maps"),
    FixtureCase("CI-01b", _ci01b_pass, _ci01b_violation, "a registry req the spec never declared"),
    FixtureCase("CI-02", _ci02_pass, _ci02_violation, "two packages own one file with no handover"),
    FixtureCase("CI-02b", _ci02b_pass, _ci02b_violation, "a produced file no glob claims"),
    FixtureCase("CI-03", _ci03_pass, _ci03_violation, "two producers for one contract version"),
    FixtureCase("CI-03b", _ci03b_pass, _ci03b_violation, "one error-code number issued twice"),
    FixtureCase("CI-03c", _ci03c_pass, _ci03c_violation, "a contract outside the canonical 13"),
    FixtureCase(
        "CI-03d", _ci03d_pass, _ci03d_violation, "3A schemas not stale on a primitive bump"
    ),
    FixtureCase("CI-04", _ci04_pass, _ci04_violation, "a real work package with an empty gate[]"),
    FixtureCase("CI-04b", _ci04b_pass, _ci04b_violation, "a CG-* with no evidence artifact"),
    FixtureCase("CI-04c", _ci04c_pass, _ci04c_violation, "a CG letter beyond the acceptance count"),
    FixtureCase("CI-04d", _ci04d_pass, _ci04d_violation, "an OUT record citing no decision"),
    FixtureCase("CI-05", _ci05_pass, _ci05_violation, "a gate with no negative branch"),
    FixtureCase("CI-05b", _ci05b_pass, _ci05b_violation, "a spawns target no catalogue defines"),
    FixtureCase("CI-05c", _ci05c_pass, _ci05c_violation, "a PG-* with only PASS and SUPERSEDED"),
    FixtureCase(
        "CI-05d", _ci05d_pass, _ci05d_violation, "an invented WP-<original>R retry package"
    ),
    FixtureCase("CI-05e", _ci05e_pass, _ci05e_violation, "DEGRADED_ACCEPTED on a CG-*"),
    FixtureCase("CI-06", _ci06_pass, _ci06_violation, "an absent artifact without planned: true"),
    FixtureCase("CI-07", _ci07_pass, _ci07_violation, "a ledger requirement with no hash"),
    FixtureCase("CI-08", _ci08_pass, _ci08_violation, "a floating ^ version in consumes[]"),
    FixtureCase("CI-09", _ci09_pass, _ci09_violation, "frozen content differing from its hash"),
    FixtureCase("CI-10", _ci10_pass, _ci10_violation, "M-8 occupying a gate declaration site"),
    FixtureCase(
        "CI-11",
        _ci11_pass,
        _ci11_violation,
        "an annotated constant citing no evidence, beside one that does",
    ),
    FixtureCase("CI-11b", _ci11b_pass, _ci11b_violation, "bare PG-RT-001 at a declaration site"),
    FixtureCase(
        "CI-11b-자기적용",
        _ci11b_self_pass,
        _ci11b_self_violation,
        "a canonical document flagged by CI-11b at a declaration site",
    ),
    FixtureCase(
        "CI-11c", _ci11c_pass, _ci11c_violation, "provisional gate without the final trigger"
    ),
    FixtureCase("CI-12", _ci12_pass, _ci12_violation, "PG-IK-001 with two of four targets"),
    FixtureCase("CI-14", _ci14_pass, _ci14_violation, "SHAPE-CF declared AI-on-HW"),
    FixtureCase(
        "CI-14b", _ci14b_pass, _ci14b_violation, "registry shape disagreeing with catalogue"
    ),
    FixtureCase("CI-14c", _ci14c_pass, _ci14c_violation, "downstream[] drifting between records"),
    FixtureCase("CI-15", _ci15_pass, _ci15_violation, "a SHAPE-MS stage owning write paths"),
    FixtureCase("CI-16", _ci16_pass, _ci16_violation, "a downstream edge with no reference"),
    FixtureCase("CI-17", _ci17_pass, _ci17_violation, "a spec_ref citing a nonexistent section"),
    FixtureCase("CI-18", _ci18_pass, _ci18_violation, "a non-BOOT package started before the gate"),
)

# CI-13 is a property of a commit rather than of a state, so its fixtures are
# expressed as changed-path sets rather than corpora; `tests/boot03` drives it.
COMMIT_SCOPED_RULES = ("CI-13",)

# Exemption fixtures: these must stay green, and each guards a specific
# over-blocking failure that would otherwise flood the report.
EXEMPTION_CASES = (
    ("CI-04", _ci04_deferred_exempt, "DEFERRED records carry no acceptance gate"),
    ("CI-07", _ci07_deferred_exempt, "DEFERRED records need no normalization hash"),
)

STAGE_CASES = (("CI-14", _ci14_stage_violation, "a non-compliant second stage must be caught"),)
