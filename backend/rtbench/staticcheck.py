"""Static proof that no frequency value drives a pass/fail verdict (NORM-008 `ci_static`).

`docs/v1/plan/normalization/ledger.yaml` NORM-008 rules that a frequency is measured and
surfaced, never used as a pass line: the 1 kHz collision-loop figure and the `f_max x 0.8`
ceiling are figures a reader judges once the measurement exists, not bars the code enforces
today. That is an absence, so it is checked by reading every decision in the tree rather
than by observing that one run happened to refuse nothing.

The unit the scan reports is a *frequency condition*, in one of three forms:

  * a comparison with one operand naming a frequency — an identifier ending `_hz`,
    including one buried in an arithmetic term such as `0.95 * target_hz` — against a real
    bar, where `None` and numeric zero are excluded because a presence or positivity guard
    on a malformed request is not a pass line;
  * a call to a function whose own `return` is such a comparison. Without this,
    `if point.in_main_path()` and `if point.target_hz >= LOW_HZ` are the same decision
    while only the second is visible;
  * a name bound to either of the above elsewhere in the same module. Every sink reads one
    expression, so binding the condition to a local and spelling the bare name in the sink
    empties all six sinks at once — `too_fast = target_hz > CAP` then `if too_fast: raise`
    is the same decision as raising on the comparison itself. Bindings chain to a fixed
    point, so hoisting twice does not evade either.

A frequency condition is a violation when it reaches one of six sinks:

  * `raise` — a branch that ends the run: a `raise`, a call to `exit`/`quit`/`_exit`/
    `abort`, or a call to a function in the same module that transitively does one of
    those. Read on `if`, `while` and `match` guards, across every branch the guard selects
    and at any depth. Named for the form it takes in nearly every case.
  * `assert` — the condition asserted rather than measured.
  * `gate_state` — a branch selecting a `GATE_STATE_*` name or one of the gate-state
    strings this package actually renders, imported from `constants` rather than re-typed
    here so a renamed state cannot leave the scan hunting for a string the code no longer
    writes.
  * `verdict_function` — the returned expression of a function whose name announces it
    answers "was this good enough". A function returning `achieved_hz >= required_hz`
    raises nothing and asserts nothing, and is exactly the shape the ruling forbids.
  * `filter` — the condition choosing which measured samples reach a verdict: a
    comprehension `if`, a `filter()` predicate, or an `if` whose branch `continue`s.
    Dropping a measured failure for its frequency decides the outcome as surely as
    refusing the run does, and it does so wherever on the path to the verdict it sits.
  * `verdict_field` — a published field whose name announces a pass/fail outcome and whose
    value carries the condition, spelled as a dict key or passed as a constructor keyword.
    A permit is a verdict even when nothing raises.

Reporting a condition that a further test also guards is deliberate: on a property that
must be zero, an over-report costs a reader one look and a miss costs the whole lock.

What the scan cannot see, stated rather than implied:

  * A predicate resolves one level. A function whose `return` only delegates to another
    predicate is not recognised as one, and a bool carried through a dataclass field into
    a `raise` in another module is invisible.
  * Abort helpers and bindings resolve within one module. A condition bound in one module
    and imported into another reads as an ordinary name, and a binding is matched by name
    across the module rather than by scope, so a same-named local elsewhere in the file is
    reported too.
  * `VERDICT_FUNCTION_PREFIXES` and `VERDICT_FIELD_MARKERS` are name vocabularies and a
    rename evades them. The other four sinks match statement shape, so neither a rename
    nor nesting the abort nor inverting the test reaches them.
  * A verdict that moves because the band handed to it moved states nothing in any single
    expression. That half is held by behaviour instead:
    `tests/wp104/test_no_frequency_gate.py` pins the overrun rate, moves the frequency, and
    requires both the status not to follow and every measured point to reach the judge.

Callers pass production roots only. A test tree legitimately builds the banned shapes —
the positive controls that prove this scanner fires are among them.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from backend.rtbench.constants import GATE_STATE_PASS, GATE_STATE_RETRY_WITH_VARIANT

PYTHON_GLOB = "*.py"

# An identifier ending here names a frequency. Case-folded before matching so a parameter
# (`target_hz`) and a module constant (`MAIN_PATH_BAND_LOW_HZ`) are both caught.
FREQUENCY_IDENTIFIER_SUFFIX = "_hz"

# Function-name prefixes that announce the function answers "was the frequency good enough"
# with a bool.
VERDICT_FUNCTION_PREFIXES = ("meets_", "passes_", "is_pass", "enforce_")

# Substrings that mark a published field as carrying a pass/fail outcome rather than a
# measurement. Matched case-folded against dict keys and constructor keywords.
VERDICT_FIELD_MARKERS = ("status", "verdict", "permit", "passed", "escalation", "within_budget")

# What a branch carries when it is selecting a gate verdict rather than computing a value.
GATE_STATE_PREFIX = "GATE_STATE_"
GATE_STATE_LITERALS = frozenset({GATE_STATE_PASS, GATE_STATE_RETRY_WITH_VARIANT})

# Callee names that end the run without an exception object, bare (`exit(1)`) or qualified
# (`sys.exit`, `os._exit`, `os.abort`). Matched on the trailing name alone, which is what
# survives both import styles.
ABORT_CALL_NAMES = frozenset({"exit", "quit", "_exit", "abort"})

FILTER_CALL_NAME = "filter"

SINK_RAISE = "raise"
SINK_ASSERT = "assert"
SINK_GATE_STATE = "gate_state"
SINK_VERDICT_FUNCTION = "verdict_function"
SINK_FILTER = "filter"
SINK_VERDICT_FIELD = "verdict_field"


@dataclass(frozen=True)
class ConditionVocabulary:
    """The names a frequency condition can stand behind at a sink.

    Attributes:
        predicates: Functions whose own `return` compares a frequency against a bar,
            collected across the whole scanned set because the call site and the
            definition routinely sit in different modules.
        bindings: Names assigned such a condition, collected per module because a hoist
            is a same-file refactor and a package-wide set would report unrelated locals.
    """

    predicates: frozenset[str]
    bindings: frozenset[str]


@dataclass(frozen=True)
class FrequencyVerdictSite:
    """One place where a frequency value decides a pass/fail outcome.

    Attributes:
        path: The file the condition was found in.
        line: One-based line number of the condition.
        symbol: The frequency identifier that drove the decision, or the predicate whose
            call stood in for it.
        sink: What the condition decided — `raise`, `assert`, `gate_state`, `filter`,
            `verdict_function:<name>`, or `verdict_field:<name>`.
    """

    path: Path
    line: int
    symbol: str
    sink: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.symbol} -> {self.sink}"


def scan_frequency_verdicts(roots: tuple[Path, ...]) -> list[FrequencyVerdictSite]:
    """Scan Python sources for frequency values driving a verdict; the count must be zero.

    Args:
        roots: Directories to scan recursively for `*.py`. A root that does not exist is
            skipped, so a caller may name an optional tree without guarding it.

    Returns:
        (list[FrequencyVerdictSite]) Every site found, sorted by path and line, empty when
        the tree measures frequency without judging on it.
    """
    modules = _parse_modules(roots)
    predicates = _frequency_predicate_names(modules)
    sites: set[FrequencyVerdictSite] = set()
    for path, tree in modules:
        sites.update(_scan_module(path, tree, predicates))
    return sorted(sites, key=_site_order)


def _parse_modules(roots: tuple[Path, ...]) -> list[tuple[Path, ast.Module]]:
    """Parse every module under the roots once, so both passes read the same trees.

    Args:
        roots: The directories to scan.

    Returns:
        (list[tuple[Path, ast.Module]]) Each file with its parsed tree, in path order.
    """
    modules: list[tuple[Path, ast.Module]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob(PYTHON_GLOB)):
            modules.append((path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))))
    return modules


def _site_order(site: FrequencyVerdictSite) -> tuple[str, int, str]:
    """Sort key placing sites in file-then-line reading order.

    Args:
        site: The site to order.

    Returns:
        (tuple[str, int, str]) Path, line, and sink.
    """
    return (str(site.path), site.line, site.sink)


def _frequency_predicate_names(modules: list[tuple[Path, ast.Module]]) -> frozenset[str]:
    """Collect the functions whose own `return` is a frequency compared against a bar.

    Names are collected across the whole scanned set and matched bare, because the call
    site writes `point.in_main_path()` and the definition lives in another module. One
    level only: a predicate that delegates to another predicate is not recognised.

    Args:
        modules: The parsed modules.

    Returns:
        (frozenset[str]) The predicate names a call may stand in for a comparison with.
    """
    names: set[str] = set()
    for _, tree in modules:
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if any(
                statement.value is not None and _carries_frequency_comparison(statement.value)
                for statement in _returns_in_scope(node)
            ):
                names.add(node.name)
    return frozenset(names)


def _bound_condition_names(tree: ast.Module, predicates: frozenset[str]) -> frozenset[str]:
    """Collect the module's names that hold a frequency condition.

    Iterated to a fixed point so `too_fast = target_hz > CAP` followed by `refuse = too_fast`
    binds both names; a single pass would let one extra hoist evade the scan.

    Args:
        tree: The parsed module.
        predicates: The frequency-predicate names a call may stand in for.

    Returns:
        (frozenset[str]) Names a bare mention of which is a frequency condition.
    """
    assignments = [
        (targets, node.value)
        for node in ast.walk(tree)
        if (targets := _assigned_names(node)) and node.value is not None
    ]
    bound: set[str] = set()
    grew = True
    while grew:
        grew = False
        for targets, value in assignments:
            if targets <= bound:
                continue
            if _carries_condition(value, ConditionVocabulary(predicates, frozenset(bound))):
                bound.update(targets)
                grew = True
    return frozenset(bound)


def _assigned_names(node: ast.AST) -> frozenset[str]:
    """Extract the plain names one assignment statement binds.

    Attribute and subscript targets are skipped: they are state reached through an object
    rather than a local standing in for the expression at a nearby sink.

    Args:
        node: Any AST node; non-assignments yield nothing.

    Returns:
        (frozenset[str]) The bound names.
    """
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign | ast.NamedExpr):
        targets = [node.target]
    else:
        return frozenset()
    names: set[str] = set()
    for target in targets:
        for element in ast.walk(target):
            if isinstance(element, ast.Name):
                names.add(element.id)
    return frozenset(names)


def _carries_condition(expression: ast.expr, vocabulary: ConditionVocabulary) -> bool:
    """Report whether an expression holds a frequency condition in any of its three forms.

    Args:
        expression: The expression to read.
        vocabulary: The predicate and binding names in scope.

    Returns:
        (bool) True when a comparison, a predicate call, or a bound name appears inside it.
    """
    return any(
        _condition_symbol(node, vocabulary) is not None
        for node in ast.walk(expression)
        if isinstance(node, ast.Compare | ast.Call | ast.Name)
    )


def _carries_frequency_comparison(expression: ast.expr) -> bool:
    """Report whether an expression compares a frequency against a real bar.

    Args:
        expression: The expression to read.

    Returns:
        (bool) True when a qualifying comparison appears anywhere inside it.
    """
    return any(
        isinstance(node, ast.Compare) and _frequency_threshold_symbol(node) is not None
        for node in ast.walk(expression)
    )


def _scan_module(
    path: Path, tree: ast.Module, predicates: frozenset[str]
) -> list[FrequencyVerdictSite]:
    """Find every frequency-driven verdict in one module.

    Args:
        path: The file the tree came from.
        tree: The parsed module.
        predicates: The frequency-predicate names a call may stand in for.

    Returns:
        (list[FrequencyVerdictSite]) The sites in this module, unsorted.
    """
    aborting = _aborting_function_names(tree)
    vocabulary = ConditionVocabulary(predicates, _bound_condition_names(tree, predicates))
    sites: list[FrequencyVerdictSite] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            sites.extend(_sites_in(path, node.test, SINK_ASSERT, vocabulary))
        elif isinstance(node, ast.If | ast.While):
            branches = (*node.body, *node.orelse)
            sites.extend(_branch_sites(path, node.test, branches, aborting, vocabulary))
        elif isinstance(node, ast.match_case):
            if node.guard is not None:
                branches = tuple(node.body)
                sites.extend(_branch_sites(path, node.guard, branches, aborting, vocabulary))
        elif isinstance(node, ast.IfExp):
            if _carries_gate_state((node.body, node.orelse)):
                sites.extend(_sites_in(path, node.test, SINK_GATE_STATE, vocabulary))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            sites.extend(_verdict_function_sites(path, node, vocabulary))
        elif isinstance(node, ast.comprehension):
            for condition in node.ifs:
                sites.extend(_sites_in(path, condition, SINK_FILTER, vocabulary))
        elif isinstance(node, ast.Call):
            sites.extend(_filter_call_sites(path, node, vocabulary))
        elif isinstance(node, ast.Dict):
            sites.extend(_verdict_field_sites(path, node, vocabulary))
        elif isinstance(node, ast.keyword):
            sites.extend(_verdict_keyword_sites(path, node, vocabulary))
    return sites


def _branch_sites(
    path: Path,
    test: ast.expr,
    branches: tuple[ast.stmt, ...],
    aborting: frozenset[str],
    vocabulary: ConditionVocabulary,
) -> list[FrequencyVerdictSite]:
    """Report a frequency-conditioned test whose branches render a verdict or drop a sample.

    Args:
        path: The file being scanned.
        test: The condition guarding the branches.
        branches: The statements of every branch the test selects between.
        aborting: Names of same-module functions that abort.
        vocabulary: The predicate and binding names a condition may stand behind.

    Returns:
        (list[FrequencyVerdictSite]) One site per frequency condition in the test, per sink
        the branches carry.
    """
    sites: list[FrequencyVerdictSite] = []
    if _carries_abort(branches, aborting):
        sites.extend(_sites_in(path, test, SINK_RAISE, vocabulary))
    if _carries_gate_state(branches):
        sites.extend(_sites_in(path, test, SINK_GATE_STATE, vocabulary))
    if _carries_skip(branches):
        sites.extend(_sites_in(path, test, SINK_FILTER, vocabulary))
    return sites


def _aborting_function_names(tree: ast.Module) -> frozenset[str]:
    """Collect the module's own functions that end the run, following helper chains.

    Iterated to a fixed point so a bar guarded by `_refuse()` which calls `_fail()` which
    raises is still an abort. Names, not objects: the call site may reach the helper as a
    bare name or as an attribute on `self`.

    Args:
        tree: The parsed module.

    Returns:
        (frozenset[str]) Names of functions in this module that abort.
    """
    definitions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    aborting: set[str] = set()
    grew = True
    while grew:
        grew = False
        for name, node in definitions.items():
            if name in aborting:
                continue
            if _carries_abort(tuple(node.body), frozenset(aborting)):
                aborting.add(name)
                grew = True
    return frozenset(aborting)


def _carries_abort(nodes: tuple[ast.AST, ...], aborting: frozenset[str]) -> bool:
    """Report whether a branch ends the run, at any depth and on either side.

    Both halves matter for the same reason: a bar that aborts is the banned shape whether
    the abort sits directly under the test, one branch deeper, or on the `else` side of an
    inverted test.

    Args:
        nodes: The statements of the branches.
        aborting: Names of same-module functions that abort.

    Returns:
        (bool) True when any branch raises, exits, or calls a helper that does.
    """
    abort_names = ABORT_CALL_NAMES | aborting
    for root in nodes:
        for node in ast.walk(root):
            if isinstance(node, ast.Raise):
                return True
            if isinstance(node, ast.Call) and _callee_name(node) in abort_names:
                return True
    return False


def _carries_skip(nodes: tuple[ast.AST, ...]) -> bool:
    """Report whether a branch drops the current sample instead of judging it.

    Args:
        nodes: The statements of the branches.

    Returns:
        (bool) True when any branch contains a `continue`.
    """
    return any(isinstance(node, ast.Continue) for root in nodes for node in ast.walk(root))


def _callee_name(node: ast.Call) -> str | None:
    """Extract the trailing name of whatever a call invokes.

    Args:
        node: The call.

    Returns:
        (str | None) `f` for `f(...)` and `m` for `obj.m(...)`, else None.
    """
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _filter_call_sites(
    path: Path, node: ast.Call, vocabulary: ConditionVocabulary
) -> list[FrequencyVerdictSite]:
    """Report a `filter()` whose predicate drops samples on their frequency.

    Args:
        path: The file being scanned.
        node: The call.
        vocabulary: The predicate and binding names a condition may stand behind.

    Returns:
        (list[FrequencyVerdictSite]) One site per frequency condition in the predicate.
    """
    if _callee_name(node) != FILTER_CALL_NAME or not node.args:
        return []
    return _sites_in(path, node.args[0], SINK_FILTER, vocabulary)


def _verdict_field_sites(
    path: Path, node: ast.Dict, vocabulary: ConditionVocabulary
) -> list[FrequencyVerdictSite]:
    """Report a published dict field whose name announces a verdict and whose value judges.

    Args:
        path: The file being scanned.
        node: The dict literal.
        vocabulary: The predicate and binding names a condition may stand behind.

    Returns:
        (list[FrequencyVerdictSite]) One site per frequency condition in a verdict field.
    """
    sites: list[FrequencyVerdictSite] = []
    for key, value in zip(node.keys, node.values, strict=True):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            continue
        if not _names_a_verdict_field(key.value):
            continue
        sites.extend(_sites_in(path, value, f"{SINK_VERDICT_FIELD}:{key.value}", vocabulary))
    return sites


def _verdict_keyword_sites(
    path: Path, node: ast.keyword, vocabulary: ConditionVocabulary
) -> list[FrequencyVerdictSite]:
    """Report a constructor keyword naming a verdict field whose value judges a frequency.

    Args:
        path: The file being scanned.
        node: The keyword argument.
        vocabulary: The predicate and binding names a condition may stand behind.

    Returns:
        (list[FrequencyVerdictSite]) One site per frequency condition in the value.
    """
    if node.arg is None or not _names_a_verdict_field(node.arg):
        return []
    return _sites_in(path, node.value, f"{SINK_VERDICT_FIELD}:{node.arg}", vocabulary)


def _names_a_verdict_field(name: str) -> bool:
    """Report whether a field name announces a pass/fail outcome.

    Args:
        name: A dict key or keyword-argument name.

    Returns:
        (bool) True when it carries one of the verdict markers.
    """
    folded = name.casefold()
    return any(marker in folded for marker in VERDICT_FIELD_MARKERS)


def _verdict_function_sites(
    path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef, vocabulary: ConditionVocabulary
) -> list[FrequencyVerdictSite]:
    """Report a frequency condition returned from a function that names itself a verdict.

    Only the function's own returns are read; a nested definition is scanned in its own
    right when `ast.walk` reaches it, and inheriting the outer name would misattribute it.

    Args:
        path: The file being scanned.
        node: The function definition.
        vocabulary: The predicate and binding names a condition may stand behind.

    Returns:
        (list[FrequencyVerdictSite]) One site per frequency condition returned.
    """
    if not node.name.startswith(VERDICT_FUNCTION_PREFIXES):
        return []
    sink = f"{SINK_VERDICT_FUNCTION}:{node.name}"
    sites: list[FrequencyVerdictSite] = []
    for statement in _returns_in_scope(node):
        if statement.value is not None:
            sites.extend(_sites_in(path, statement.value, sink, vocabulary))
    return sites


def _returns_in_scope(node: ast.AST) -> Iterator[ast.Return]:
    """Yield the `return` statements belonging to one function, not to nested ones.

    Args:
        node: The function definition, or a statement inside it.

    Yields:
        (ast.Return) Each return in this scope.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(child, ast.Return):
            yield child
        yield from _returns_in_scope(child)


def _sites_in(
    path: Path, expression: ast.expr, sink: str, vocabulary: ConditionVocabulary
) -> list[FrequencyVerdictSite]:
    """Find the frequency conditions inside one expression.

    Args:
        path: The file being scanned.
        expression: The expression occupying a verdict sink.
        sink: The sink label to attribute the sites to.
        vocabulary: The predicate and binding names a condition may stand behind.

    Returns:
        (list[FrequencyVerdictSite]) One site per qualifying condition.
    """
    sites: list[FrequencyVerdictSite] = []
    for node in ast.walk(expression):
        if not isinstance(node, ast.Compare | ast.Call | ast.Name):
            continue
        symbol = _condition_symbol(node, vocabulary)
        if symbol is not None:
            sites.append(
                FrequencyVerdictSite(path=path, line=node.lineno, symbol=symbol, sink=sink)
            )
    return sites


def _condition_symbol(
    node: ast.Compare | ast.Call | ast.Name, vocabulary: ConditionVocabulary
) -> str | None:
    """Identify the frequency a single node conditions on, in whichever form it takes.

    Args:
        node: A comparison, a call, or a bare name inside a sink expression.
        vocabulary: The predicate and binding names a condition may stand behind.

    Returns:
        (str | None) The frequency identifier, the predicate name, or the bound name.
    """
    if isinstance(node, ast.Compare):
        return _frequency_threshold_symbol(node)
    if isinstance(node, ast.Name):
        return node.id if node.id in vocabulary.bindings else None
    name = _callee_name(node)
    return name if name in vocabulary.predicates else None


def _frequency_threshold_symbol(node: ast.Compare) -> str | None:
    """Identify the frequency this comparison measures against a real bar.

    A chained comparison is treated as one site: the first frequency operand names it, and
    any other operand that is not `None`-or-zero makes it a bar rather than a guard.

    Args:
        node: The comparison under inspection.

    Returns:
        (str | None) The frequency identifier, or None when this is not a frequency
        compared against a real bar.
    """
    operands: list[ast.expr] = [node.left, *node.comparators]
    for index, operand in enumerate(operands):
        symbol = _frequency_symbol(operand)
        if symbol is None:
            continue
        for other_index, other in enumerate(operands):
            if other_index != index and _is_real_threshold(other):
                return symbol
    return None


def _frequency_symbol(node: ast.expr) -> str | None:
    """Extract the frequency identifier an operand resolves to.

    Arithmetic is descended into so `0.95 * target_hz` counts as the frequency it scales,
    which is the ordinary way a ratio bar is written.

    Args:
        node: The operand expression.

    Returns:
        (str | None) The `_hz` identifier, or None.
    """
    if isinstance(node, ast.Name):
        return node.id if _names_a_frequency(node.id) else None
    if isinstance(node, ast.Attribute):
        return node.attr if _names_a_frequency(node.attr) else None
    if isinstance(node, ast.Call):
        return _frequency_symbol(node.func)
    if isinstance(node, ast.BinOp):
        left = _frequency_symbol(node.left)
        return left if left is not None else _frequency_symbol(node.right)
    if isinstance(node, ast.UnaryOp):
        return _frequency_symbol(node.operand)
    return None


def _names_a_frequency(identifier: str) -> bool:
    """Report whether an identifier names a frequency.

    Args:
        identifier: A variable, attribute, or function name.

    Returns:
        (bool) True when it ends in the frequency suffix, in any case.
    """
    return identifier.casefold().endswith(FREQUENCY_IDENTIFIER_SUFFIX)


def _is_real_threshold(node: ast.expr) -> bool:
    """Report whether an operand is a bar rather than a presence or positivity guard.

    `x is None` and `x <= 0` are how malformed input is rejected; neither states that a
    frequency was too low or too high to pass, so neither is what NORM-008 forbids.

    Args:
        node: The operand being compared against.

    Returns:
        (bool) True when the operand is a real bar.
    """
    if not isinstance(node, ast.Constant):
        return True
    value = node.value
    if value is None or isinstance(value, bool):
        return False
    return not (isinstance(value, int | float) and value == 0)


def _carries_gate_state(nodes: tuple[ast.AST, ...]) -> bool:
    """Report whether a branch selects a gate state rather than computing a value.

    Args:
        nodes: The statements or expressions of the branches.

    Returns:
        (bool) True when a `GATE_STATE_*` name or a bare gate-state literal appears.
    """
    for root in nodes:
        for node in ast.walk(root):
            if isinstance(node, ast.Name) and node.id.startswith(GATE_STATE_PREFIX):
                return True
            if isinstance(node, ast.Attribute) and node.attr.startswith(GATE_STATE_PREFIX):
                return True
            if isinstance(node, ast.Constant) and _is_gate_state_literal(node.value):
                return True
    return False


def _is_gate_state_literal(value: object) -> bool:
    """Report whether a constant is one of this package's bare gate-state strings.

    Args:
        value: The constant's value.

    Returns:
        (bool) True for a string in `GATE_STATE_LITERALS`.
    """
    return isinstance(value, str) and value in GATE_STATE_LITERALS
