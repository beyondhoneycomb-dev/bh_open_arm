"""WP-2C-01 negative branch: a separate-process placement is caught statically (FAIL_BLOCKING).

The residual must be computed inside the CAN-bus-owning process; a separate process with its own
CAN socket is a second silent bind (FR-SAF-001). The only honest check of that absence is static,
so these tests assert the real GMO tree is clean and that the scan actually bites the two families
it forbids — process spawning and bus/socket opening.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.gmo import (
    SeparateProcessBindingError,
    assert_single_process_binding,
    check_source,
    scan_tree,
)
from backend.gmo.single_process import RULE_SECOND_BIND, RULE_SEPARATE_PROCESS

_GMO_ROOT = Path(__file__).resolve().parents[2] / "backend" / "gmo"


def test_real_gmo_tree_is_clean() -> None:
    """The shipped GMO package names no process-spawn or bus/socket symbol."""
    assert scan_tree(_GMO_ROOT) == ()
    assert_single_process_binding(_GMO_ROOT)


def test_scan_bites_process_spawn() -> None:
    """A `multiprocessing.Process` reference is reported as a separate-process finding."""
    source = "import multiprocessing\n\n\ndef go():\n    return multiprocessing.Process()\n"
    findings = check_source(source, "candidate.py")
    rules = {finding.rule for finding in findings}
    assert RULE_SEPARATE_PROCESS in rules
    assert {finding.symbol for finding in findings} >= {"multiprocessing", "Process"}


def test_scan_bites_subprocess_and_pool() -> None:
    """subprocess and a process pool are separate-process findings too."""
    source = (
        "import subprocess\n"
        "from concurrent.futures import ProcessPoolExecutor\n\n\n"
        "def go():\n"
        "    subprocess.Popen(['x'])\n"
        "    return ProcessPoolExecutor()\n"
    )
    findings = check_source(source, "candidate.py")
    assert all(finding.rule == RULE_SEPARATE_PROCESS for finding in findings)
    assert {finding.symbol for finding in findings} >= {"subprocess", "Popen"}


def test_scan_bites_second_bind() -> None:
    """A raw/CAN socket or python-can bus is reported as a second-bind finding."""
    source = (
        "import socket\n"
        "import can\n\n\n"
        "def go():\n"
        "    s = socket.socket(socket.AF_CAN, socket.SOCK_RAW)\n"
        "    s.bind(('can0',))\n"
        "    return can.interface.Bus()\n"
    )
    findings = check_source(source, "candidate.py")
    rules = {finding.rule for finding in findings}
    assert rules == {RULE_SECOND_BIND}
    symbols = {finding.symbol for finding in findings}
    assert symbols >= {"socket", "can", "AF_CAN", "SOCK_RAW", "bind", "Bus"}


def test_assert_raises_on_a_dirty_tree(tmp_path: Path) -> None:
    """`assert_single_process_binding` raises when a scanned tree contains a violation."""
    (tmp_path / "leaky.py").write_text("import multiprocessing\n")
    with pytest.raises(SeparateProcessBindingError):
        assert_single_process_binding(tmp_path)


def test_symbols_in_comments_and_strings_do_not_trip(tmp_path: Path) -> None:
    """The AST scan ignores forbidden words that appear only in comments or strings."""
    source = "# this module must never call multiprocessing.Process or socket.bind\nX = 'Bus'\n"
    assert check_source(source, "candidate.py") == []
