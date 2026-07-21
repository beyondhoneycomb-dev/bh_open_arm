"""Acceptance ④⑤ — the MJCF invariant checker and its non-vacuity.

④ Every joint's joint-class motor equals its actuator's motor: zero violations on
the fixed asset. ⑤ J7's resolved dynamics are the DM4310 centre, never the typo
triple whose armature is 0.0049.

The checker must earn trust: run against a J7-reverted copy of the same asset it
reports the contradiction on both arms. A checker that cannot fail is worthless.
"""

from __future__ import annotations

import re

from sim.mjcf.invariant import (
    STATUS_KNOWN_DIVERGENCE,
    STATUS_VIOLATION,
    TYPO_MOTOR_CLASS,
    audit,
)
from tests.wp0c03 import BIMANUAL_XML

_J7_CLASS = re.compile(r'(<joint name="openarm_(?:left|right)_joint7"[^>]*class=")motor_DM4310(")')


def _reverted_to_typo() -> str:
    """Return the fixed asset text with only J7 reverted to the DM3507 typo."""
    text = BIMANUAL_XML.read_text(encoding="utf-8")
    reverted = _J7_CLASS.sub(rf"\g<1>{TYPO_MOTOR_CLASS}\g<2>", text)
    joint_refs = re.findall(rf'<joint\b[^>]*class="{TYPO_MOTOR_CLASS}"', reverted)
    assert len(joint_refs) == 2
    return reverted


def test_fixed_asset_has_zero_violations() -> None:
    report = audit(BIMANUAL_XML)
    violations = [f for f in report.consistency if f.status == STATUS_VIOLATION]
    assert violations == []
    assert report.ok, report.failures


def test_gripper_divergence_is_named_not_hidden() -> None:
    report = audit(BIMANUAL_XML)
    divergences = {f.joint for f in report.consistency if f.status == STATUS_KNOWN_DIVERGENCE}
    assert divergences == {"openarm_left_finger_joint1", "openarm_right_finger_joint1"}


def test_checker_flags_the_reverted_typo() -> None:
    report = audit(_reverted_to_typo())
    assert not report.ok
    flagged = {f.joint for f in report.consistency if f.status == STATUS_VIOLATION}
    assert flagged == {"openarm_left_joint7", "openarm_right_joint7"}


def test_reverted_typo_rejected_as_dr_source() -> None:
    report = audit(_reverted_to_typo())
    typo_failures = [f for f in report.failures if "0.0049" in f]
    assert len(typo_failures) == 2


def test_fixed_asset_j7_not_typo_dynamics() -> None:
    report = audit(BIMANUAL_XML)
    assert not any("0.0049" in failure for failure in report.failures)
