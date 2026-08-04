"""NORM-006 and NORM-007: the two normalization rulings whose enforcement is `ci_static`.

Deliberately not a `CI-*` rule. `06` §5 declares `CI-01`..`CI-18` and nothing else, and
`registry/checks/__init__.py` makes the roster a two-way contract — an executable for a
rule the canon does not declare is as much a violation as a declared rule with no
executable. So this is a library that `tests/boot03/test_norm_enforcement.py` runs under
the `pytest` gate, not a roster entry. Promoting it into `registry.check` requires `06`
§5 to declare the rule first, and the ledger's `enforcement.status` cannot read `active`
until that happens: `registry/normalization/validator.py` resolves an active `check` to
a `registry/checks/ci_*.py` file and nothing else.

The scope of each gate is narrow on purpose, and the narrowness is the design:

* Requirement text arrives through `registry.ingest.spec.parse_all`, so a "cell" is a
  row of a declaration table and never a sentence of prose. Both ledger predicates say
  field parsing, and `06` §5 records why twice already (CI-10, CI-11b): a lexical sweep
  detonates on the paragraphs that document the ban.
* Neither `전원 차단` nor `하드 E-Stop` is banned at large. Both appear in requirements
  the ledger ruled surviving — FR-GUI-064 keeps the standing drop warning, FR-GUI-093
  explains why process death is a drop, and FR-GUI-111 itself carries the clause
  forbidding power cut as the default collision reaction. A wider ban would make the
  cheapest way to clear a red gate the deletion of a safety warning, which is the one
  outcome a safety check must never reward.
* `frontend/src/screens/S-12/reactionPolicy.ts` names a `POWER_OFF` reaction mode and is
  not a target. `12` §2.10 defines that path as CAN `disable_all()` (`0xFD`), a torque
  cut owned by `12` FR-SAF-037/042. NORM-007 rules on a boundary absent from `13` §2.7;
  the CAN bus is in that manifest.

Every gate reports an empty sample as a violation instead of passing vacuously. This
data is always supposed to be present, so "nothing to look at" means the checker broke,
not that the rule holds. Counting is not enough for the frontend scan — a path typo
walks an empty tree and reports green — so the scan also confirms by name that it
reached the two files a regression would land in.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from registry import NORMALIZATION_SUBPATH
from registry.checks.corpus import Corpus
from registry.ingest.markdown import Table, all_tables, plain_text
from registry.ingest.spec import Requirement
from registry.ingest.spec import parse_all as parse_spec
from registry.normalization.loader import load_ledger
from registry.normalization.validator import Violation

NORM_006 = "NORM-006"
NORM_007 = "NORM-007"

LEDGER_RELPATH = NORMALIZATION_SUBPATH / "ledger.yaml"

GUI_SPEC_DOC = "13"
GUI_CATALOG_PREFIX = "02d"
GUI_WORK_PACKAGE = "WP-G-03"

# The word NORM-006 retired. One requirement used it for the torque-holding stop and the
# next for the power cut that drops the payload, and thirteen parallel screen
# implementers each resolved it their own way while every resolution passed CG-G-03b.
AMBIGUOUS_STOP_WORD = "비상정지"

# What replaced it on the soft side: the stop the backend applies while holding torque.
SOFT_STOP_IDENTIFIER = "STOP_HOLD"

REACHABILITY_CHECK = "CG-G-03b"
ACCEPTANCE_CHECK_ID = re.compile(r"CG-G-03[a-z]")

COLLISION_POLICY_REQ = "FR-GUI-111"
HARD_ESTOP_TOKEN = "하드 E-Stop"

# `13` §2.7 calls itself this system's complete set of network boundaries. It is located
# by its first column rather than by section number, so a renumbered heading empties the
# sample loudly instead of silently.
PORT_MANIFEST_FIRST_COLUMN = "경계"

# Boundary hardware `13` §2.7 does not list. A requirement naming one of these assumes an
# actuation or sensing path the rig has no port for. The manifest is re-read on every
# run, so the day a relay row is added the gate goes quiet on its own — because the
# hardware changed, not because the check was edited.
ABSENT_BOUNDARY_HARDWARE = ("릴레이", "컨택터", "안전 PLC", "GPIO", "E-Stop 접점")

FRONTEND_SUBPATH = Path("frontend") / "src"
SCANNED_SUFFIXES = (".ts", ".tsx")
TEST_FILE_MARKER = ".test."

# Handler props and call sites that would mean the browser can actuate a power cut. Named
# symbols only: identifiers and prose that merely mention a power cut are how the rig
# documents the hazard it cannot remove.
POWER_CUT_ACTUATION = (
    re.compile(r"on(?:(?:Hard)?E[-_]?Stop|PowerCut|PowerOff)"),
    re.compile(
        r"\b(?:send|emit|dispatch|trigger|fire|request|apply)"
        r"[A-Za-z]*(?:PowerCut|PowerOff|HardEStop)\b"
    ),
    re.compile(r"\b(?:powerCut|powerOff|hardEStop)\s*\("),
)

# The two files a NORM-007 regression lands in: the global stop pair, and the collision
# reaction policy that names a POWER_OFF mode. Confirming the scan reached them by name
# is what separates "examined the tree" from "counted 270 of something".
SCAN_ANCHORS = (
    "frontend/src/global/StopControls.tsx",
    "frontend/src/screens/S-12/reactionPolicy.ts",
)

KIND_VACUOUS = "vacuous"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*$", re.MULTILINE)


def _gui_requirements(corpus: Corpus) -> tuple[Requirement, ...]:
    """Return the requirement rows document `13` declares.

    Args:
        corpus: The corpus under test.

    Returns:
        (tuple[Requirement, ...]) Declared rows of `13`, in document order.
    """
    return tuple(req for req in parse_spec(corpus.spec_dir) if req.doc == GUI_SPEC_DOC)


def _location(corpus: Corpus, req: Requirement) -> str:
    """Render a requirement's provenance as `<file>:<line>`.

    Args:
        corpus: The corpus under test.
        req: The requirement row.

    Returns:
        (str) Root-relative path and 1-indexed line of the declaring row.
    """
    return f"{corpus.rel(req.source)}:{req.source_line}"


def _ledger_row(corpus: Corpus, norm_id: str) -> dict[str, Any]:
    """Return one row of the normalization ledger.

    Args:
        corpus: The corpus under test.
        norm_id: The `NORM-*` id to look up.

    Returns:
        (dict[str, Any]) The row, or an empty mapping when the ledger has no such row.
    """
    path = corpus.root / LEDGER_RELPATH
    if not path.is_file():
        return {}
    for row in load_ledger(path).get("rows", []):
        if row.get("norm_id") == norm_id:
            found: dict[str, Any] = row
            return found
    return {}


def _port_manifest(corpus: Corpus) -> Table | None:
    """Return the `13` §2.7 port manifest table.

    Args:
        corpus: The corpus under test.

    Returns:
        (Table | None) The manifest table, or None when `13` or the table is absent.
    """
    matches = sorted(corpus.spec_dir.glob(f"{GUI_SPEC_DOC}-*.md"))
    if not matches:
        return None
    for table in all_tables(matches[0]):
        if table.header and plain_text(table.header[0]).strip() == PORT_MANIFEST_FIRST_COLUMN:
            return table
    return None


def strip_comments(text: str) -> str:
    """Blank out comments while keeping every line at its original number.

    Block comments collapse to their own newlines rather than to nothing, because the
    findings carry `<file>:<line>` and a reader who is sent to the wrong line stops
    trusting the report. Mirrors the stripping
    `frontend/src/global/staticChecks.test.ts` applies, including its `(?<!:)` guard,
    which keeps `https://` in a string from swallowing the rest of the line.

    Args:
        text: Source text of a TypeScript file.

    Returns:
        (str) The same text with comment bodies removed and line count preserved.
    """
    without_blocks = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return _LINE_COMMENT.sub("", without_blocks)


def scanned_frontend_files(corpus: Corpus) -> tuple[Path, ...]:
    """Return the frontend sources NORM-007 applies to.

    Test files are excluded: `frontend/src/global/staticChecks.test.ts` asserts the very
    symbols banned here, so a scan that included tests would fail on the assertion that
    the symbols are absent.

    Args:
        corpus: The corpus under test.

    Returns:
        (tuple[Path, ...]) Sorted non-test `.ts`/`.tsx` files under `frontend/src`.
    """
    root = corpus.root / FRONTEND_SUBPATH
    if not root.is_dir():
        return ()
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.suffix in SCANNED_SUFFIXES and TEST_FILE_MARKER not in path.name and path.is_file()
    )


def check_norm_006(corpus: Corpus) -> list[Violation]:
    """Report where the retired word `비상정지` still decides something.

    Three gates, all field-parsed: the requirement cells of `13`, the acceptance cells of
    `02d`, and the subject of `CG-G-03b` — the 208-combination reachability check, which
    guarantees nothing while the thing it makes reachable is still the ambiguous word.

    Args:
        corpus: The corpus under test.

    Returns:
        (list[Violation]) Unenforced claims, sample failures first.
    """
    violations: list[Violation] = []

    requirements = _gui_requirements(corpus)
    ruled = tuple(
        str(item["req"])
        for item in _ledger_row(corpus, NORM_006).get("discarded", [])
        if item.get("req")
    )
    declared = {req.req_id for req in requirements}
    missing = sorted(set(ruled) - declared)
    if not requirements or missing:
        violations.append(
            Violation(
                NORM_006,
                KIND_VACUOUS,
                f"parsed {len(requirements)} requirement cell(s) from spec {GUI_SPEC_DOC}"
                f" and did not reach the ruled requirement(s) {missing}",
            )
        )

    for req in requirements:
        if AMBIGUOUS_STOP_WORD in req.text:
            violations.append(
                Violation(
                    NORM_006,
                    "ambiguous-stop-word",
                    f"{_location(corpus, req)} {req.req_id} still decides with "
                    f"{AMBIGUOUS_STOP_WORD!r}, which names both the torque-holding stop "
                    f"and the power cut; say {SOFT_STOP_IDENTIFIER} or say the physical "
                    "button",
                )
            )

    violations.extend(_check_gui_acceptance(corpus))
    return violations


def _check_gui_acceptance(corpus: Corpus) -> list[Violation]:
    """Judge the `02d` acceptance cell of `WP-G-03` and the subject of `CG-G-03b`.

    Only the acceptance column. `02d`'s frozen-contract column carries the same word in
    the same row and is outside the ruling's stated scope, so passing this gate is not
    the same as the word being gone from `02d`. Widening the predicate here would be the
    checker rewriting the ruling it enforces.

    Args:
        corpus: The corpus under test.

    Returns:
        (list[Violation]) Unenforced claims for the GUI work package.
    """
    entry = corpus.catalog.get(GUI_WORK_PACKAGE)
    if entry is None or not entry.source.name.startswith(GUI_CATALOG_PREFIX):
        return [
            Violation(
                NORM_006,
                KIND_VACUOUS,
                f"{GUI_WORK_PACKAGE} has no row in the {GUI_CATALOG_PREFIX} catalog",
            )
        ]

    acceptance = entry.acceptance_text
    where = f"{corpus.rel(entry.source)}:{entry.source_line}"
    violations: list[Violation] = []
    if not acceptance.strip():
        return [
            Violation(
                NORM_006, KIND_VACUOUS, f"{where} {GUI_WORK_PACKAGE} acceptance cell is empty"
            )
        ]

    if AMBIGUOUS_STOP_WORD in acceptance:
        violations.append(
            Violation(
                NORM_006,
                "ambiguous-stop-word",
                f"{where} {GUI_WORK_PACKAGE} acceptance cell still decides with "
                f"{AMBIGUOUS_STOP_WORD!r}",
            )
        )

    clause = reachability_clause(acceptance)
    if clause is None:
        violations.append(
            Violation(
                NORM_006,
                KIND_VACUOUS,
                f"{where} acceptance cell declares no {REACHABILITY_CHECK} clause to read",
            )
        )
    elif SOFT_STOP_IDENTIFIER not in clause:
        violations.append(
            Violation(
                NORM_006,
                "unfixed-reachability-subject",
                f"{where} {REACHABILITY_CHECK} does not name {SOFT_STOP_IDENTIFIER} as what "
                f"stays reachable, so its 208 combinations certify an undecided subject: "
                f"{clause.strip()!r}",
            )
        )
    return violations


def reachability_clause(acceptance: str) -> str | None:
    """Cut the `CG-G-03b` clause out of an acceptance cell.

    The cell enumerates every `CG-G-03*` check in one paragraph, so the clause has to end
    at the next acceptance id. Reading to the end of the cell instead would let a
    `STOP_HOLD` belonging to some later check answer for this one, and `CG-G-03b` is the
    check whose 208 combinations are worthless while its subject is undecided.

    Args:
        acceptance: Raw acceptance column text.

    Returns:
        (str | None) The clause, or None when the cell declares no `CG-G-03b`.
    """
    start = acceptance.find(REACHABILITY_CHECK)
    if start < 0:
        return None
    following = ACCEPTANCE_CHECK_ID.search(acceptance, start + len(REACHABILITY_CHECK))
    return acceptance[start : following.start()] if following else acceptance[start:]


def check_norm_007(corpus: Corpus) -> list[Violation]:
    """Report GUI claims that presuppose a power-cut boundary the rig does not have.

    Four gates: the readings the ledger discarded must be gone from the cells they were
    quoted from; `FR-GUI-111` must not offer a hard E-Stop as a selectable collision
    reaction; no `13` requirement may name boundary hardware `13` §2.7 omits; and no
    frontend source may expose a symbol that actuates a power cut.

    Args:
        corpus: The corpus under test.

    Returns:
        (list[Violation]) Unenforced claims, sample failures first.
    """
    requirements = _gui_requirements(corpus)
    by_id = {req.req_id: req for req in requirements}
    violations: list[Violation] = []

    discarded = [
        item for item in _ledger_row(corpus, NORM_007).get("discarded", []) if item.get("req")
    ]
    unreachable = sorted({str(item["req"]) for item in discarded} - set(by_id))
    if not discarded or unreachable:
        violations.append(
            Violation(
                NORM_007,
                KIND_VACUOUS,
                f"read {len(discarded)} discarded reading(s) from the ledger and did not "
                f"reach the requirement(s) {unreachable}",
            )
        )

    for item in discarded:
        req = by_id.get(str(item["req"]))
        quote = str(item["quote"])
        if req is not None and quote in plain_text(req.text):
            violations.append(
                Violation(
                    NORM_007,
                    "discarded-reading-alive",
                    f"{_location(corpus, req)} {req.req_id} still states the reading the "
                    f"ledger discarded: {quote!r}",
                )
            )

    violations.extend(_check_collision_policy(corpus, by_id))
    violations.extend(_check_absent_boundary(corpus, requirements))
    violations.extend(_check_frontend_actuation(corpus))
    return violations


def _check_collision_policy(corpus: Corpus, by_id: dict[str, Requirement]) -> list[Violation]:
    """Judge the collision reaction policy `FR-GUI-111` enumerates.

    The token is banned, the phrase `전원 차단` in the same cell is not: it belongs to the
    clause that forbids power cut as the default reaction, which is the ruling being
    enforced rather than a violation of it.

    Args:
        corpus: The corpus under test.
        by_id: Requirement rows of `13`, keyed by id.

    Returns:
        (list[Violation]) A violation when the policy still offers a hard E-Stop.
    """
    req = by_id.get(COLLISION_POLICY_REQ)
    if req is None:
        return [
            Violation(
                NORM_007,
                KIND_VACUOUS,
                f"{COLLISION_POLICY_REQ} has no declaration row in spec {GUI_SPEC_DOC}",
            )
        ]
    if HARD_ESTOP_TOKEN not in req.text:
        return []
    return [
        Violation(
            NORM_007,
            "power-cut-policy-option",
            f"{_location(corpus, req)} {COLLISION_POLICY_REQ} offers {HARD_ESTOP_TOKEN!r} as a "
            "selectable collision reaction, which requires a software power-cut path the "
            "port manifest has no boundary for",
        )
    ]


def _check_absent_boundary(
    corpus: Corpus, requirements: tuple[Requirement, ...]
) -> list[Violation]:
    """Judge `13` requirements against the boundaries `13` §2.7 actually declares.

    The manifest is checked first and on every run. If a relay row ever appears there,
    that word stops being evidence of an assumed boundary and the gate stops reporting
    it — the check is bound to the hardware, not to a fixed list of forbidden words.

    Args:
        corpus: The corpus under test.
        requirements: Requirement rows of `13`.

    Returns:
        (list[Violation]) One violation per requirement naming absent hardware.
    """
    manifest = _port_manifest(corpus)
    if manifest is None or not manifest.rows:
        return [
            Violation(
                NORM_007,
                KIND_VACUOUS,
                f"spec {GUI_SPEC_DOC} declares no port manifest table to read boundaries from",
            )
        ]

    listed = " ".join(plain_text(cell) for row in manifest.rows for cell in row)
    absent = tuple(word for word in ABSENT_BOUNDARY_HARDWARE if word not in listed)
    return [
        Violation(
            NORM_007,
            "unlisted-boundary",
            f"{_location(corpus, req)} {req.req_id} names {word!r}, which the port manifest "
            f"of {GUI_SPEC_DOC} §2.7 does not list among this system's boundaries",
        )
        for req in requirements
        for word in absent
        if word in req.text
    ]


def _check_frontend_actuation(corpus: Corpus) -> list[Violation]:
    """Judge the frontend sources for a symbol that actuates a power cut.

    Args:
        corpus: The corpus under test.

    Returns:
        (list[Violation]) One violation per matching symbol, sample failures first.
    """
    files = scanned_frontend_files(corpus)
    scanned = {corpus.rel(path) for path in files}
    unreached = sorted(anchor for anchor in SCAN_ANCHORS if anchor not in scanned)
    violations: list[Violation] = []
    if not files or unreached:
        violations.append(
            Violation(
                NORM_007,
                KIND_VACUOUS,
                f"scanned {len(files)} frontend source(s) and never reached {unreached}",
            )
        )

    for path in files:
        code = strip_comments(path.read_text(encoding="utf-8"))
        for number, line in enumerate(code.splitlines(), start=1):
            for pattern in POWER_CUT_ACTUATION:
                match = pattern.search(line)
                if match:
                    violations.append(
                        Violation(
                            NORM_007,
                            "power-cut-actuation-symbol",
                            f"{corpus.rel(path)}:{number} declares {match.group(0)!r}, a symbol "
                            "that actuates a power cut the rig has no boundary for",
                        )
                    )
    return violations
