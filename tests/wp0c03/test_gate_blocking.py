"""Acceptance ⑨ — friction identification is blocked until PG-J7-001 is decided.

Two halves. The registry half: the gate graph binds PG-J7-001 to WP-0C-03 (where
the asset is fixed) and gates the Wave 2B friction-identification work on it, so a
friction run cannot precede the J7 decision. The asset half: the invariant checker
is the concrete block — pointed at an unfixed asset it fails, which is what stops
friction identification from running on a contaminated model.
"""

from __future__ import annotations

import json
import re

from sim.mjcf.invariant import TYPO_MOTOR_CLASS, audit
from tests.wp0c03 import BIMANUAL_XML, GATE_INDEX

PG_J7 = "PG-J7-001"
FRICTION_GATE = "PG-FRIC-001"
WAVE_2B_PREFIX = "WP-2B-"

_J7_CLASS = re.compile(r'(<joint name="openarm_(?:left|right)_joint7"[^>]*class=")motor_DM4310(")')


def _gate_entry(gate_id: str) -> dict[str, list[str]]:
    index = json.loads(GATE_INDEX.read_text(encoding="utf-8"))["index"]
    return index[gate_id]


def test_pg_j7_bound_to_this_wp_and_its_measurer() -> None:
    entry = _gate_entry(PG_J7)
    work_packages = set(entry["work_packages"])
    assert "WP-0C-03" in work_packages  # the asset fix decides the gate
    assert "WP-0B-07" in work_packages  # the RID-23 measurement feeds it


def test_wave2b_friction_work_gated_on_pg_j7() -> None:
    entry = _gate_entry(PG_J7)
    gated = set(entry["work_packages"]) | set(entry["descendants"])
    friction_band = {wp for wp in gated if wp.startswith(WAVE_2B_PREFIX)}
    assert friction_band, "no Wave 2B work package is gated on PG-J7-001"


def test_friction_gate_sits_behind_pg_j7() -> None:
    # WP-2B-07 carries both PG-FRIC-001 and PG-J7-001, so the friction gate cannot
    # clear without the J7 gate having been evaluated first.
    pg_j7_wps = set(_gate_entry(PG_J7)["work_packages"]) | set(_gate_entry(PG_J7)["descendants"])
    friction_wps = set(_gate_entry(FRICTION_GATE)["work_packages"])
    assert friction_wps & pg_j7_wps


def test_checker_blocks_an_unfixed_asset() -> None:
    text = BIMANUAL_XML.read_text(encoding="utf-8")
    unfixed = _J7_CLASS.sub(rf"\g<1>{TYPO_MOTOR_CLASS}\g<2>", text)
    report = audit(unfixed)
    assert not report.ok
