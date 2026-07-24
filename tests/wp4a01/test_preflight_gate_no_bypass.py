"""CG-4A-03d (extended, static) — no submit->RUNNING path skips the clearance.

WP-4A-03 proved statically that a `TrainingClearance` is minted only inside
`clear_for_training`. That guarantee bound only callers routing *through* the gate;
it explicitly could not reach the orchestrator's launch path, which WP-4A-01 owns
(and WP-4A-03 must not edit). OBS-1 is exactly that missing half: this test extends
the no-bypass proof to the launch path itself, parsing the orchestrator package and
proving four structural facts:

  (a) the orchestrator constructs a `TrainingClearance` NOWHERE — it can only receive
      one from `clear_for_training`, so it cannot fabricate the token;
  (b) every trainer launch and every transition to RUNNING is lexically inside the
      single guarded site `_launch_running` — no other function starts a run;
  (c) `_launch_running` takes a REQUIRED `TrainingClearance` parameter, so it is
      unreachable without a token in hand;
  (d) every call to `_launch_running` passes a clearance freshly minted by
      `clear_for_training` in the same function — not a fabricated or reused value.

Together these make "a job reaches RUNNING only holding a clearance" a property of the
code's shape, not of a caller's discipline. The check is exercised both ways: it PASSes
on the real source and BITEs on each injected bypass.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "backend" / "training" / "orchestrator"

# The one guarded launch site, the token, and its sole mint function.
LAUNCH_FN = "_launch_running"
TOKEN = "TrainingClearance"
MINT_FN = "clear_for_training"
# The AST tokens a launch / RUNNING-transition is spelt with.
LAUNCH_ATTR = "launch"
SET_STATE_FN = "_set_state"
STATE_ENUM = "JobState"
RUNNING_ATTR = "RUNNING"


class LaunchBypassError(AssertionError):
    """Raised when a source exposes a path to RUNNING that skips the clearance."""


def _is_call_to(call: ast.Call, name: str) -> bool:
    """Whether a call targets `name`, as a bare name or an attribute (`self.name`)."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == name
    if isinstance(func, ast.Attribute):
        return func.attr == name
    return False


def _is_running_literal(node: ast.AST | None) -> bool:
    """Whether a node is the `JobState.RUNNING` enum member."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == RUNNING_ATTR
        and isinstance(node.value, ast.Name)
        and node.value.id == STATE_ENUM
    )


def _annotation_is(annotation: ast.AST | None, name: str) -> bool:
    """Whether a parameter annotation names `name` (bare or attribute)."""
    if isinstance(annotation, ast.Name):
        return annotation.id == name
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == name
    return False


class _Analyzer(ast.NodeVisitor):
    """Collects launch-path facts, attributing each to its enclosing function."""

    def __init__(self) -> None:
        self.mFuncStack: list[str] = []
        self.mClearanceConstructions: list[str] = []
        self.mRunningTransitions: list[str] = []
        self.mLaunchCalls: list[str] = []
        self.mLaunchRunningCalls: list[tuple[str, ast.expr | None]] = []
        self.mMintedNames: dict[str, set[str]] = defaultdict(set)
        self.mLaunchRunningDefs: list[ast.FunctionDef] = []

    def _enclosing(self) -> str:
        return self.mFuncStack[-1] if self.mFuncStack else ""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast visitor API
        if node.name == LAUNCH_FN:
            self.mLaunchRunningDefs.append(node)
        self.mFuncStack.append(node.name)
        self.generic_visit(node)
        self.mFuncStack.pop()

    def _record_mint_and_transition(self, target: ast.AST | None, value: ast.AST | None) -> None:
        minted = (
            isinstance(value, ast.Call)
            and _is_call_to(value, MINT_FN)
            and isinstance(target, ast.Name)
        )
        if minted:
            self.mMintedNames[self._enclosing()].add(target.id)  # type: ignore[union-attr]
        if _is_running_literal(value):
            self.mRunningTransitions.append(self._enclosing())

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802 - ast visitor API
        for target in node.targets:
            self._record_mint_and_transition(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802 - ast visitor API
        self._record_mint_and_transition(node.target, node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast visitor API
        if _is_call_to(node, TOKEN):
            self.mClearanceConstructions.append(self._enclosing())
        if isinstance(node.func, ast.Attribute) and node.func.attr == LAUNCH_ATTR:
            self.mLaunchCalls.append(self._enclosing())
        if _is_call_to(node, SET_STATE_FN) and any(_is_running_literal(arg) for arg in node.args):
            self.mRunningTransitions.append(self._enclosing())
        if _is_call_to(node, LAUNCH_FN):
            clearance_arg = node.args[1] if len(node.args) >= 2 else None
            self.mLaunchRunningCalls.append((self._enclosing(), clearance_arg))
        self.generic_visit(node)


def analyze(sources: dict[str, str]) -> _Analyzer:
    """Parse every source and collect its launch-path facts into one analyzer."""
    analyzer = _Analyzer()
    for name, text in sources.items():
        analyzer.visit(ast.parse(text, filename=name))
    return analyzer


def _has_required_clearance_param(defn: ast.FunctionDef) -> bool:
    """Whether `_launch_running` takes a REQUIRED `TrainingClearance` parameter."""
    positional = list(defn.args.posonlyargs) + list(defn.args.args)
    first_defaulted = len(positional) - len(defn.args.defaults)
    for index, arg in enumerate(positional):
        if _annotation_is(arg.annotation, TOKEN):
            return index < first_defaulted
    return False


def assert_no_launch_bypass(sources: dict[str, str]) -> None:
    """Raise `LaunchBypassError` if any source can reach RUNNING without a clearance.

    Args:
        sources: Map of filename to source text to analyse together.

    Raises:
        LaunchBypassError: On a fabricated token, a launch/RUNNING transition outside
            the guarded site, a `_launch_running` without a required clearance
            parameter, or a `_launch_running` call passing a non-minted value.
    """
    analyzer = analyze(sources)

    if analyzer.mClearanceConstructions:
        raise LaunchBypassError(
            f"{TOKEN} is constructed outside {MINT_FN} (in {analyzer.mClearanceConstructions}); "
            "the orchestrator could fabricate a clearance and skip the gate"
        )

    stray_launch = [fn for fn in analyzer.mLaunchCalls if fn != LAUNCH_FN]
    if stray_launch:
        raise LaunchBypassError(
            f"a trainer launch happens outside {LAUNCH_FN} (in {stray_launch}); "
            "a run can start without holding a clearance"
        )

    stray_running = [fn for fn in analyzer.mRunningTransitions if fn != LAUNCH_FN]
    if stray_running:
        raise LaunchBypassError(
            f"a transition to {STATE_ENUM}.{RUNNING_ATTR} happens outside {LAUNCH_FN} "
            f"(in {stray_running}); a job can reach RUNNING without a clearance"
        )

    for defn in analyzer.mLaunchRunningDefs:
        if not _has_required_clearance_param(defn):
            raise LaunchBypassError(
                f"{LAUNCH_FN} does not take a required {TOKEN} parameter; it could be "
                "entered without a clearance"
            )

    for enclosing, clearance_arg in analyzer.mLaunchRunningCalls:
        minted = analyzer.mMintedNames.get(enclosing, set())
        if not (isinstance(clearance_arg, ast.Name) and clearance_arg.id in minted):
            raise LaunchBypassError(
                f"{LAUNCH_FN} is called in {enclosing!r} with a clearance not minted by "
                f"{MINT_FN}; the token could be fabricated or reused"
            )


def _package_sources() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8") for path in sorted(_PACKAGE_DIR.glob("*.py"))
    }


def test_real_orchestrator_has_no_bypass() -> None:
    sources = _package_sources()
    assert_no_launch_bypass(sources)

    # The check is not vacuous: the guarded site exists, it is the sole launcher, and
    # the gate (clear_for_training) is genuinely invoked to feed it.
    analyzer = analyze(sources)
    assert analyzer.mLaunchRunningDefs, f"no {LAUNCH_FN} site — the check would be vacuous"
    assert analyzer.mLaunchCalls, "no trainer launch anywhere — the check would be vacuous"
    assert all(fn == LAUNCH_FN for fn in analyzer.mLaunchCalls)
    assert analyzer.mLaunchRunningCalls, f"{LAUNCH_FN} is never called — dead launch path"
    assert analyzer.mMintedNames, f"{MINT_FN} is never called — the gate is not wired"


_BYPASS_FABRICATED_TOKEN = """
class TrainingOrchestrator:
    def _run_preflight_gate(self, runtime):
        clearance = TrainingClearance(reviewed_findings=(), decisions=())
        self._launch_running(runtime, clearance)

    def _launch_running(self, runtime, clearance: TrainingClearance):
        self.mLauncher.launch((), (), None)
        self._set_state(runtime, JobState.RUNNING)
"""

_BYPASS_LAUNCH_OUTSIDE_GUARD = """
class TrainingOrchestrator:
    def _dispatch(self, runtime, gpus):
        self.mLauncher.launch((), gpus, None)
        self._set_state(runtime, JobState.RUNNING)
"""

_BYPASS_DIRECT_STATE_ASSIGN = """
class TrainingOrchestrator:
    def _dispatch(self, runtime, gpus):
        runtime.spec.state = JobState.RUNNING
"""

_BYPASS_NON_MINTED_TOKEN = """
class TrainingOrchestrator:
    def _run_preflight_gate(self, runtime):
        fake = object()
        self._launch_running(runtime, fake)

    def _launch_running(self, runtime, clearance: TrainingClearance):
        self.mLauncher.launch((), (), None)
        self._set_state(runtime, JobState.RUNNING)
"""

_BYPASS_OPTIONAL_CLEARANCE = """
class TrainingOrchestrator:
    def _run_preflight_gate(self, runtime):
        clearance = clear_for_training(r, f, d)
        self._launch_running(runtime, clearance)

    def _launch_running(self, runtime, clearance: TrainingClearance = None):
        self.mLauncher.launch((), (), None)
        self._set_state(runtime, JobState.RUNNING)
"""

_LEGIT_PATTERN = """
class TrainingOrchestrator:
    def _run_preflight_gate(self, runtime):
        clearance = clear_for_training(r, f, d)
        self._launch_running(runtime, clearance)

    def _launch_running(self, runtime, clearance: TrainingClearance):
        self.mLauncher.launch((), (), None)
        self._set_state(runtime, JobState.RUNNING)
"""


@pytest.mark.parametrize(
    "bypass",
    [
        _BYPASS_FABRICATED_TOKEN,
        _BYPASS_LAUNCH_OUTSIDE_GUARD,
        _BYPASS_DIRECT_STATE_ASSIGN,
        _BYPASS_NON_MINTED_TOKEN,
        _BYPASS_OPTIONAL_CLEARANCE,
    ],
)
def test_check_bites_on_injected_bypass(bypass: str) -> None:
    with pytest.raises(LaunchBypassError):
        assert_no_launch_bypass({"injected.py": bypass})


def test_check_accepts_the_legit_pattern() -> None:
    # The guarded pattern the real orchestrator uses must not itself be flagged.
    assert_no_launch_bypass({"legit.py": _LEGIT_PATTERN})
