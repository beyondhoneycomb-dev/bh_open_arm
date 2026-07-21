"""Acceptance ① — the J7 class fix is present on both arms in the vendored asset.

The criterion is textual: joint 7 references ``motor_DM4310`` on both arms (two
hits) and ``motor_DM3507`` survives only as its ``<default>`` definition, with zero
references. This mirrors the grep the plan spells out.
"""

from __future__ import annotations

import re

from tests.wp0c03 import BIMANUAL_XML

J7_LINE = re.compile(r'<joint name="openarm_(left|right)_joint7"[^>]*class="([^"]+)"')


def test_joint7_references_dm4310_on_both_arms() -> None:
    text = BIMANUAL_XML.read_text(encoding="utf-8")
    classes = dict(J7_LINE.findall(text))
    assert classes == {"left": "motor_DM4310", "right": "motor_DM4310"}


def test_no_remaining_reference_to_typo_class() -> None:
    text = BIMANUAL_XML.read_text(encoding="utf-8")
    # The <default class="motor_DM3507"> definition may remain; every *reference*
    # (a joint carrying class="motor_DM3507") must be gone.
    assert re.search(r'<joint\b[^>]*class="motor_DM3507"', text) is None


def test_typo_default_definition_may_remain_but_only_as_definition() -> None:
    text = BIMANUAL_XML.read_text(encoding="utf-8")
    occurrences = text.count("motor_DM3507")
    definitions = text.count('<default class="motor_DM3507">')
    assert occurrences == definitions == 1
