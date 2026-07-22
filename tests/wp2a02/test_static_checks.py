"""Static acceptance — ⑤ latch cleared only by re-arm, ⑥ expiry path free of client clock.

Two of this WP's guarantees are structural, and the acceptance criteria ask for them
to be checked statically rather than only exercised: that the sole path clearing the
latch is the re-arm confirmation (⑤), and that no expiry decision reads a
client-supplied timestamp (⑥). Both are checked here by reading the source of the
relevant methods, which is why the code deliberately quarantines every
`issued_mono_client` use into the age filter and every latch clear into
`confirm_rearm` — so a source-level check is decisive.

The ⑥ check is on the *code*, not the text: it parses the AST and looks for a real
reference (a name, attribute, argument, or keyword) to the client-clock field, so a
docstring that mentions the field to state it is never used does not count as use.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from types import ModuleType

from backend.actuation.lease import LeaseManager
from backend.deadman.age_filter import ClientClockOffset
from backend.deadman.controller import DeadmanController
from backend.deadman.monitor import DeadmanMonitor
from backend.deadman.receiver import RenewalReceiver

_CLIENT_CLOCK_TOKEN = "issued_mono_client"


def _references_client_clock(source: str) -> bool:
    """Whether the source, parsed as code, references the client-clock field.

    Docstrings and comments are ignored — only a `Name`, `Attribute`, argument, or
    keyword bearing the token counts, so prose that names the field to say it is
    unused is not a reference.

    Args:
        source: Python source for a module, class, or function.

    Returns:
        (bool) True if any code node references the client-clock field.
    """
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == _CLIENT_CLOCK_TOKEN:
            return True
        if isinstance(node, ast.Name) and node.id == _CLIENT_CLOCK_TOKEN:
            return True
        if isinstance(node, ast.arg) and node.arg == _CLIENT_CLOCK_TOKEN:
            return True
        if isinstance(node, ast.keyword) and node.arg == _CLIENT_CLOCK_TOKEN:
            return True
    return False


def _source(target: Callable[..., object] | type | ModuleType) -> str:
    """Return the source of a function, class, or module."""
    return inspect.getsource(target)


def _controller_methods() -> dict[str, str]:
    """Source of every regular method on the controller, keyed by name."""
    return {
        name: inspect.getsource(fn)
        for name, fn in inspect.getmembers(DeadmanController, predicate=inspect.isfunction)
    }


def test_latch_is_cleared_only_by_confirm_rearm() -> None:
    """`acknowledge_latch` is called from exactly one place: `confirm_rearm` (⑤)."""
    methods = _controller_methods()
    callers = sorted(name for name, src in methods.items() if "acknowledge_latch()" in src)
    assert callers == ["confirm_rearm"]

    # And exactly once in the whole class, so no property getter clears it either.
    class_source = _source(DeadmanController)
    assert class_source.count("self._latch_target.acknowledge_latch()") == 1


def test_latch_is_engaged_only_from_the_expiry_path() -> None:
    """`engage_safety_latch` is called from exactly one place: the expiry check (⑤)."""
    methods = _controller_methods()
    callers = sorted(name for name, src in methods.items() if "engage_safety_latch(" in src)
    assert callers == ["_latch_if_expired"]


def test_expiry_path_has_no_client_clock_reference() -> None:
    """No expiry-deciding code references the client-supplied timestamp (⑥)."""
    expiry_path = {
        "DeadmanMonitor": _source(DeadmanMonitor),
        "DeadmanController.poll": _source(DeadmanController.poll),
        "DeadmanController._latch_if_expired": _source(DeadmanController._latch_if_expired),
        "DeadmanController._expiry_reason": _source(DeadmanController._expiry_reason),
        "LeaseManager.is_expired": _source(LeaseManager.is_expired),
    }
    for where, source in expiry_path.items():
        assert not _references_client_clock(source), f"client clock referenced in {where}"


def test_monitor_module_holds_no_client_clock_reference() -> None:
    """The expiry-to-latch bridge module references no client-clock field in code (⑥)."""
    module = inspect.getmodule(DeadmanMonitor)
    assert module is not None
    assert not _references_client_clock(_source(module))


def test_client_clock_is_actually_used_somewhere() -> None:
    """Guard against a vacuous ⑥: the client clock IS referenced, just not for expiry."""
    assert _references_client_clock(_source(ClientClockOffset.age))
    assert _references_client_clock(_source(RenewalReceiver.receive))
