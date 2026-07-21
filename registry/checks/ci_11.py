"""CI-11 — no target before measurement: a threshold must cite its evidence hash.

`00` invariant I-6 forbids fixing a target before measuring it, and `NFR-PRF-053`
is the requirement behind this rule. The rule is anchored rather than semantic:
it fires only where an anchor exists, meaning a constant declaration annotated
`@target` or `@threshold` inside a package gated on one of the measurement gates
that produce evidence hashes. Such a constant must reference the gate's PASS
evidence directory, otherwise the number is a wish that outranks the measurement.

`06` §5 names the *declaration* as the unit under judgement, so the annotation and
the evidence reference are both attributed to one declaration. Judging the
enclosing file instead is wrong in both directions: a single correctly anchored
constant would excuse every other threshold sharing its file, and a file that only
writes the word — a table of annotation tokens, a docstring explaining this rule —
would be held to a requirement `06` §5 never placed on it.

An annotation counts only when a comment attached to the declaration carries it. A
string literal spelling the token is data about the rule and a docstring is
documentation of it; neither declares a target.

`06` §5 is explicit that a threshold which cannot carry an anchor is not a CI
matter at all — it moves to acceptance review (§8, F-2 class). So an unannotated
constant is out of scope by design and is not a silent pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from registry.checks.corpus import Corpus
from registry.checks.globs import expand, split_globs
from registry.checks.model import Finding, RuleResult, fail

RULE_ID = "CI-11"
TITLE = "no target before measurement"

# `06` §5 names these gates as the anchored set: each produces a PASS evidence hash.
ANCHOR_GATES = ("PG-RT-001a", "PG-RT-001b", "PG-IK-001", "PG-STO-001")

TARGET_ANNOTATIONS = ("@target", "@threshold")

EVIDENCE_ROOT = "registry/build/evidence"

# Comment syntax is per language family, and reading a C header with Python rules
# would take `#define` for a comment and blind the rule to every macro constant.
_HASH_COMMENT_SUFFIXES = frozenset({".py", ".yaml", ".yml", ".toml"})
_SLASH_COMMENT_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".c", ".h", ".cpp", ".hpp", ".json"})
_TEXT_SUFFIXES = _HASH_COMMENT_SUFFIXES | _SLASH_COMMENT_SUFFIXES

# Suffixes whose constants are mapping entries rather than assignments.
_MAPPING_SUFFIXES = frozenset({".yaml", ".yml", ".json"})

_HASH_MARKER = "#"
_SLASH_MARKER = "//"

_TRIPLE_QUOTES = ('"""', "'''")

_QUOTES = "\"'"

_ESCAPE = "\\"

# `NAME = value`, optionally type-annotated. Comparison and augmented-assignment
# operators are excluded so that `budget <= MAX` does not read as a declaration.
_ASSIGNMENT = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]*)?(?<![=!<>+*/%&|^-])=(?![=>])"
)

_MAPPING_KEY = re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*\S")

_MACRO_DEFINE = re.compile(r"^\s*#\s*define\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s")

# A quoted mapping key is a declaration, so its text has to survive the pass that
# strips string contents. Restricting what survives to identifier shapes is what
# keeps an annotation token spelled as a string value from surviving with it — such
# a token is being named, not applied, and no identifier shape can contain one.
_IDENTIFIER_LITERAL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class Declaration:
    """One annotated constant declaration — the unit `06` §5 puts in scope.

    Attributes:
        line: 1-based line the declaration sits on.
        name: Declared identifier, which names the site in the report.
        anchor_text: The declaration and the comments attached to it, and nothing
            else in the file. The evidence reference is looked for here alone, so
            that a path belonging to one declaration cannot excuse another.
    """

    line: int
    name: str
    anchor_text: str


@dataclass(frozen=True)
class AnchoredSource:
    """A file in scope, paired with the gates its thresholds must cite evidence from.

    Attributes:
        wp_id: Package owning the file; the finding is attributed to it.
        gates: Measurement gates on that package's gate axis, in `ANCHOR_GATES` order.
        path: Root-relative POSIX path.
    """

    wp_id: str
    gates: tuple[str, ...]
    path: str


def _skip_string(line: str, start: int) -> int:
    """Find the end of a single-line string literal.

    Args:
        line: Source line.
        start: Index of the opening quote.

    Returns:
        (int) Index just past the closing quote, or the line length when the
        literal does not close on this line.
    """
    quote = line[start]
    index = start + 1
    while index < len(line):
        if line[index] == _ESCAPE:
            index += 2
            continue
        if line[index] == quote:
            return index + 1
        index += 1
    return len(line)


def _split_code_and_comment(line: str, marker: str, pending: str) -> tuple[str, str, str]:
    """Separate a line's code from its comment, treating string contents as neither.

    A comment marker inside a string literal opens no comment, which is the whole
    reason this is a scanner and not a `str.split`: the fixture corpora carry
    source text as Python strings, and reading their `#` as a comment would put
    the fixtures themselves in scope.

    Args:
        line: Source line without its terminator.
        marker: Comment marker for the file's language family.
        pending: Triple-quote delimiter this line starts inside of, or empty.

    Returns:
        (tuple[str, str, str]) Code with string contents dropped except for
        identifier-shaped literals, the comment text, and the triple-quote
        delimiter the next line starts inside of.
    """
    index = 0
    if pending:
        close = line.find(pending)
        if close < 0:
            return "", "", pending
        index = close + len(pending)

    code: list[str] = []
    while index < len(line):
        if line.startswith(marker, index):
            return "".join(code), line[index:], ""
        triple = next((quote for quote in _TRIPLE_QUOTES if line.startswith(quote, index)), "")
        if triple:
            close = line.find(triple, index + len(triple))
            if close < 0:
                return "".join(code), "", triple
            index = close + len(triple)
            continue
        if line[index] in _QUOTES:
            end = _skip_string(line, index)
            literal = line[index + 1 : end - 1]
            if _IDENTIFIER_LITERAL.match(literal):
                code.append(literal)
            index = end
            continue
        code.append(line[index])
        index += 1
    return "".join(code), "", ""


def _declaration_name(code: str, suffix: str) -> str:
    """Name the constant a line declares, if it declares one.

    Args:
        code: The line's code, with non-identifier string contents already dropped.
        suffix: File suffix, which decides whether mapping-entry syntax counts.

    Returns:
        (str) Declared identifier, or empty when the line declares nothing.
    """
    macro = _MACRO_DEFINE.match(code)
    if macro:
        return macro.group("name")
    if suffix in _MAPPING_SUFFIXES:
        mapping = _MAPPING_KEY.match(code)
        if mapping:
            return mapping.group("name")
    assignment = _ASSIGNMENT.search(code)
    return assignment.group("name") if assignment else ""


def annotated_declarations(text: str, suffix: str) -> tuple[Declaration, ...]:
    """Find the declarations an `@target`/`@threshold` comment is attached to.

    A comment block attaches only when it runs up to the declaration. A blank line,
    a docstring or any other statement between the two means the comment documents
    something else, and reading it as an annotation would drag unrelated constants
    into scope — the over-blocking half of `02a` §−2.3 acceptance ③.

    Args:
        text: Full file contents.
        suffix: File suffix, deciding comment and declaration syntax.

    Returns:
        (tuple[Declaration, ...]) Annotated declarations, in file order.
    """
    marker = _HASH_MARKER if suffix in _HASH_COMMENT_SUFFIXES else _SLASH_MARKER
    declarations: list[Declaration] = []
    attached: list[str] = []
    pending = ""

    for number, line in enumerate(text.splitlines(), start=1):
        code, comment, pending = _split_code_and_comment(line, marker, pending)
        if not code.strip():
            if comment:
                attached.append(comment)
            else:
                attached.clear()
            continue
        name = _declaration_name(code, suffix)
        annotation = "\n".join([*attached, comment])
        if name and any(token in annotation for token in TARGET_ANNOTATIONS):
            declarations.append(
                Declaration(line=number, name=name, anchor_text=f"{annotation}\n{code}")
            )
        attached.clear()

    return tuple(declarations)


def anchored_packages(corpus: Corpus) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """List packages whose gate axis carries a gate this rule anchors on.

    Kept separate from the source walk because the two answer different questions,
    and a vacuous result is only readable when both are known. Anchored packages
    that own no source is the honest state of a tree whose measurement code has not
    landed; no anchored package at all means the scope stopped resolving, which is
    the failure `02a` §-2.3 warns about. Deriving one number from the other collapses
    the distinction, because a package contributes to the source walk only if it
    already owns files.

    Args:
        corpus: The corpus under test.

    Returns:
        (tuple[tuple[str, tuple[str, ...]], ...]) Work-package id paired with the
        anchor gates it declares, ordered by package id.
    """
    packages: list[tuple[str, tuple[str, ...]]] = []
    for wp_id, records in sorted(corpus.by_wp.items()):
        gates = {g for record in records for g in record.get("gate", []) or []}
        anchored = tuple(gate for gate in ANCHOR_GATES if gate in gates)
        if anchored:
            packages.append((wp_id, anchored))
    return tuple(packages)


def anchored_sources(corpus: Corpus) -> tuple[AnchoredSource, ...]:
    """List the source files the rule is scoped to, with the gates each answers to.

    This is the rule's *reach*, which is a different quantity from its population of
    sites and must stay separable from it. A vacuous result means one of two
    unrelated things — no threshold has been declared yet, or the scope stopped
    resolving to files at all — and only the reach tells them apart. The second is
    the failure `02a` §−2.3 warns about; the first is the honest state of a tree
    whose measurement code has not landed.

    Args:
        corpus: The corpus under test.

    Returns:
        (tuple[AnchoredSource, ...]) Readable text sources owned by a package whose
        gate axis carries a measurement gate.
    """
    sources: list[AnchoredSource] = []

    for wp_id, anchored in anchored_packages(corpus):
        globs: set[str] = set()
        for record in corpus.by_wp[wp_id]:
            owned = list(record.get("owns", []) or [])
            for phase in record.get("phases", []) or []:
                owned.extend(phase.get("owns", []) or [])
            for entry in owned:
                globs.update(split_globs(str(entry.get("glob", ""))))

        for path in sorted(expand(tuple(sorted(globs)), corpus.tracked_files)):
            full = corpus.root / path
            if full.suffix not in _TEXT_SUFFIXES or not full.is_file():
                continue
            sources.append(AnchoredSource(wp_id=wp_id, gates=anchored, path=path))

    return tuple(sources)


def run(corpus: Corpus) -> RuleResult:
    """Report annotated threshold declarations that do not cite their evidence hash.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per unanchored annotated declaration.
    """
    findings: list[Finding] = []
    sources = anchored_sources(corpus)
    sites = 0

    for source in sources:
        text = (corpus.root / source.path).read_text(encoding="utf-8", errors="replace")
        # An annotated declaration needs its token somewhere in the file, so this
        # keeps the line scan off sources that cannot hold a site.
        if not any(token in text for token in TARGET_ANNOTATIONS):
            continue

        suffix = (corpus.root / source.path).suffix
        for declaration in annotated_declarations(text, suffix):
            sites += 1
            cited = any(
                f"{EVIDENCE_ROOT}/{gate}" in declaration.anchor_text for gate in source.gates
            )
            if cited:
                continue
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=source.wp_id,
                    path=f"{source.path}:{declaration.line}",
                    reason=(
                        "declaration is annotated as a target but cites no PASS evidence "
                        "hash for its measurement gate, so a number outranks the measurement"
                    ),
                    expected=(
                        f"{declaration.name} to cite {EVIDENCE_ROOT}/"
                        f"<{'|'.join(source.gates)}>/ in its own annotation"
                    ),
                    actual=f"{declaration.name} annotated with no evidence reference",
                )
            )

    notes: tuple[str, ...] = ()
    if not sites:
        packages = len(anchored_packages(corpus))
        reason = (
            "no package declares an anchor gate, so the scope resolved to nothing"
            if not packages
            else f"{packages} package(s) declare an anchor gate but own "
            f"{len(sources)} source file(s), and no threshold has been declared yet"
        )
        notes = (f"{reason}; the rule acquires meaning when measurement code lands.",)

    return RuleResult(
        rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites, notes=notes
    )
