"""Acceptance ⑥ — zero `get_observation` on the pattern-A tick path, and the scan bites.

Pattern A is a tick condition: the scheduler reads state from the MIT response, not a
per-cycle `get_observation` poll. The tap must not reintroduce that poll, and the scan that
enforces the absence must fire on a real call.
"""

from __future__ import annotations

from pathlib import Path

import backend.friction_log
from backend.friction_log.scheduler_tap import SchedulerLogTap
from backend.friction_log.staticcheck import RULE_GET_OBSERVATION, check_source, scan_tree

_FRICTION_LOG_ROOT = Path(backend.friction_log.__file__).resolve().parent
_TAP_MODULE = Path(SchedulerLogTap.__module__.replace(".", "/") + ".py")


def test_logger_tree_has_no_get_observation() -> None:
    """⑥ No module under `backend/friction_log` calls `get_observation`."""
    hits = [f for f in scan_tree(_FRICTION_LOG_ROOT) if f.rule == RULE_GET_OBSERVATION]
    assert hits == []


def test_pattern_a_tap_module_has_no_get_observation() -> None:
    """⑥ The pattern-A tap module specifically is clean."""
    source = (_FRICTION_LOG_ROOT.parent.parent / _TAP_MODULE).read_text(encoding="utf-8")
    hits = [f for f in check_source(source, str(_TAP_MODULE)) if f.rule == RULE_GET_OBSERVATION]
    assert hits == []


def test_scan_bites_on_get_observation_call() -> None:
    """⑥ A `get_observation` call on any object is flagged."""
    findings = check_source("frame = robot.get_observation()\n", "rogue.py")
    assert [f.rule for f in findings] == [RULE_GET_OBSERVATION]


def test_scan_bites_on_bare_get_observation_name() -> None:
    """⑥ A bare `get_observation` reference is flagged."""
    findings = check_source("fn = get_observation\n", "rogue.py")
    assert [f.rule for f in findings] == [RULE_GET_OBSERVATION]
