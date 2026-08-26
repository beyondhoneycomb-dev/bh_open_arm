"""Acceptance ⑨ — friction identification is blocked until the J7 asset is fixed.

The registry half of this file asserted the gate graph bound PG-J7-001 to this WP; that
graph is gone with the registry. What is left is the half that reads the asset: a
friction run cannot precede the J7 decision. The asset half: the invariant checker
is the concrete block — pointed at an unfixed asset it fails, which is what stops
friction identification from running on a contaminated model.
"""

from __future__ import annotations

import re

from sim.mjcf.invariant import TYPO_MOTOR_CLASS, audit
from tests.wp0c03 import BIMANUAL_XML

PG_J7 = "PG-J7-001"
FRICTION_GATE = "PG-FRIC-001"
WAVE_2B_PREFIX = "WP-2B-"

_J7_CLASS = re.compile(r'(<joint name="openarm_(?:left|right)_joint7"[^>]*class=")motor_DM4310(")')


def test_checker_blocks_an_unfixed_asset() -> None:
    text = BIMANUAL_XML.read_text(encoding="utf-8")
    unfixed = _J7_CLASS.sub(rf"\g<1>{TYPO_MOTOR_CLASS}\g<2>", text)
    report = audit(unfixed)
    assert not report.ok
