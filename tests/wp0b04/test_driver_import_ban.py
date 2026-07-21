"""Acceptance ③④ — static ban of `openarm_driver` on the canonical path.

`01` FR-SYS-010 bans `openarm_driver` (it opens its own CAN socket, a double bind
the flock cannot see) while permitting `openarm_control` and `openarm_ker`. The
scan must flag every form of the banned import and leave the two allowed packages
untouched — over-blocking the sanctioned packages is itself the acceptance-④
defect.
"""

from __future__ import annotations

from pathlib import Path

from backend.can.bind.staticcheck import BANNED_DRIVER_MODULE, find_banned_driver_import

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_static_import_is_flagged() -> None:
    """`import openarm_driver` is rejected (acceptance ③)."""
    findings = find_banned_driver_import(_FIXTURES / "canonical_imports_driver.py")
    assert [item.symbol for item in findings] == [BANNED_DRIVER_MODULE]


def test_from_import_is_flagged() -> None:
    """`from openarm_driver import …` is rejected (acceptance ③)."""
    findings = find_banned_driver_import(_FIXTURES / "canonical_imports_driver_from.py")
    assert [item.symbol for item in findings] == [BANNED_DRIVER_MODULE]


def test_dynamic_import_is_flagged() -> None:
    """`importlib.import_module("openarm_driver")` is rejected (acceptance ③)."""
    findings = find_banned_driver_import(_FIXTURES / "canonical_dynamic_driver.py")
    assert [item.symbol for item in findings] == [BANNED_DRIVER_MODULE]


def test_allowed_control_import_is_not_flagged() -> None:
    """`import openarm_control` passes — no over-block (acceptance ④)."""
    assert find_banned_driver_import(_FIXTURES / "canonical_imports_control.py") == []


def test_allowed_ker_import_is_not_flagged() -> None:
    """`import openarm_ker` passes — no over-block (acceptance ④)."""
    assert find_banned_driver_import(_FIXTURES / "canonical_imports_ker.py") == []


def test_mixed_flags_only_the_banned_import() -> None:
    """A file importing both flags exactly the banned one (acceptance ④)."""
    findings = find_banned_driver_import(_FIXTURES / "canonical_mixed_imports.py")
    assert [item.symbol for item in findings] == [BANNED_DRIVER_MODULE]


def test_live_backend_tree_imports_no_driver() -> None:
    """The real canonical product tree currently imports `openarm_driver` nowhere."""
    assert find_banned_driver_import(_REPO_ROOT / "backend") == []
