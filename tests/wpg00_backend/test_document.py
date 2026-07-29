"""The document defaults, and CG-G-00d blast-radius isolation on the read path.

The isolation is asserted in both directions on purpose. A corrupt `endEffector` must not cost
the operator their `layout`; a corrupt `layout` must not change what the rig believes is fitted.
The second direction is the one with a bus behind it.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from backend.config.constants import (
    FIELD_DENSITY,
    FIELD_MODE,
    FIELD_SIDEBAR_COLLAPSED,
    FIELD_TOOL_ID,
    FIELD_TOOL_MASS_KG,
    FIELD_VIEW_PRESETS,
    SUBOBJECT_END_EFFECTOR,
    SUBOBJECT_LAYOUT,
    SUBOBJECT_PRESETS,
    SUBOBJECT_THEME,
)
from backend.config.model import (
    SUBOBJECT_KEYS,
    ArmEndEffectorConfig,
    EndEffectorConfig,
    LayoutConfig,
    default_document,
    parse_document,
)
from backend.endeffector import (
    DEFAULT_TOOL_ID,
    SIDE_LEFT,
    SIDE_RIGHT,
    TOOL_GRIPPER,
    tool_by_id,
)
from tests.wpg00_backend.conftest import GRIPPER_ON_BOTH_ARMS, NON_DEFAULT_LAYOUT

UNREGISTERED_TOOL_ID = "vacuum_cup"


def test_default_document_puts_both_arms_on_the_no_gripper_tool() -> None:
    """Nothing chosen means the tool with no motor on `0x08`, on both arms."""
    document = default_document()

    assert document.end_effector.left.tool_id == DEFAULT_TOOL_ID
    assert document.end_effector.right.tool_id == DEFAULT_TOOL_ID
    assert tool_by_id(DEFAULT_TOOL_ID).gripper_motor is False


def test_default_document_matches_the_client_side_defaults() -> None:
    """The three shell subobjects default to what `frontend/src/config/schema.ts` defaults to."""
    wire = default_document().to_wire()

    assert wire[SUBOBJECT_LAYOUT] == {FIELD_SIDEBAR_COLLAPSED: False, FIELD_DENSITY: "comfortable"}
    assert wire[SUBOBJECT_THEME] == {FIELD_MODE: "system"}
    assert wire[SUBOBJECT_PRESETS] == {FIELD_VIEW_PRESETS: {}}


def test_malformed_end_effector_leaves_layout_intact() -> None:
    """CG-G-00d: only `endEffector` defaults; the operator's layout survives."""
    parsed = parse_document(
        {
            SUBOBJECT_LAYOUT: NON_DEFAULT_LAYOUT,
            SUBOBJECT_END_EFFECTOR: {SIDE_LEFT: {FIELD_TOOL_ID: UNREGISTERED_TOOL_ID}},
        }
    )

    assert parsed.defaulted == (SUBOBJECT_END_EFFECTOR,)
    assert parsed.document.layout.sidebar_collapsed is True
    assert parsed.document.layout.density == "compact"
    assert parsed.document.end_effector.left.tool_id == DEFAULT_TOOL_ID


def test_malformed_layout_leaves_the_fitted_tool_intact() -> None:
    """The direction with a bus behind it: a broken layout must not re-answer `0x08`."""
    parsed = parse_document(
        {
            SUBOBJECT_LAYOUT: {FIELD_SIDEBAR_COLLAPSED: "yes"},
            SUBOBJECT_END_EFFECTOR: GRIPPER_ON_BOTH_ARMS,
        }
    )

    assert parsed.defaulted == (SUBOBJECT_LAYOUT,)
    assert parsed.document.layout == LayoutConfig()
    assert parsed.document.end_effector.left.tool_id == TOOL_GRIPPER
    assert parsed.document.end_effector.right.tool_id == TOOL_GRIPPER


def test_absent_subobject_is_not_reported_as_defaulted() -> None:
    """A key nobody ever stored is not a fault — the default stands and nothing is reported."""
    parsed = parse_document({SUBOBJECT_LAYOUT: NON_DEFAULT_LAYOUT})

    assert parsed.defaulted == ()
    assert parsed.document.end_effector == EndEffectorConfig()


def test_unknown_top_level_key_is_dropped_not_fatal() -> None:
    """A stray top-level key costs nothing: refusing the document would default all four."""
    parsed = parse_document({SUBOBJECT_LAYOUT: NON_DEFAULT_LAYOUT, "screensaver": {"after_s": 30}})

    assert parsed.defaulted == ()
    assert parsed.document.layout.density == "compact"
    assert "screensaver" not in parsed.document.to_wire()


def test_non_object_document_defaults_every_subobject_and_says_so() -> None:
    """There is no structure to isolate within, so every key is reported as defaulted."""
    parsed = parse_document(["layout"])

    assert parsed.defaulted == SUBOBJECT_KEYS
    assert parsed.document == default_document()


@pytest.mark.parametrize(
    "mass",
    [0, 0.0, -0.4, True, "0.5"],
    ids=["zero-int", "zero-float", "negative", "boolean", "string"],
)
def test_tool_mass_is_a_positive_number_or_null(mass: Any) -> None:
    """Zero is refused: an unweighed tool is null, not a mass nobody measured.

    `True` and `"0.5"` are in the same list because pydantic's lax mode would otherwise turn them
    into 1.0 kg and 0.5 kg — numbers gravity compensation would subtract as if they were real.
    """
    with pytest.raises(ValidationError):
        ArmEndEffectorConfig.model_validate({FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: mass})


def test_null_tool_mass_round_trips_as_null() -> None:
    """Unmeasured stays unmeasured — it must not become a zero on the way through."""
    arm = ArmEndEffectorConfig.model_validate(
        {FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: None}
    )

    assert arm.tool_mass_kg is None
    assert arm.model_dump(by_alias=True)[FIELD_TOOL_MASS_KG] is None


def test_unregistered_tool_id_is_refused_with_the_known_ids_named() -> None:
    """The refusal has to carry the choices, or the caller cannot act on it."""
    with pytest.raises(ValidationError) as refusal:
        ArmEndEffectorConfig.model_validate({FIELD_TOOL_ID: UNREGISTERED_TOOL_ID})

    message = str(refusal.value)
    assert UNREGISTERED_TOOL_ID in message
    assert DEFAULT_TOOL_ID in message
    assert TOOL_GRIPPER in message


def test_extra_field_in_a_subobject_is_refused() -> None:
    """`extra="forbid"`: a field the model does not know is a field nothing would ever read."""
    with pytest.raises(ValidationError):
        LayoutConfig.model_validate({**NON_DEFAULT_LAYOUT, "sidebarWidthPx": 240})


def test_a_typo_in_an_arm_key_is_refused_not_ignored() -> None:
    """`extra="forbid"` on the arm model, asserted rather than assumed.

    Swapping this model to `extra="ignore"` left all 47 tests green, so a mistyped key would
    have been dropped in silence and the arm would carry the default tool. That default decides
    whether CAN id 0x08 is polled, so a dropped key is not a cosmetic loss.
    """
    document = {
        SUBOBJECT_END_EFFECTOR: {
            SIDE_LEFT: {"tooId": TOOL_GRIPPER},
            SIDE_RIGHT: {FIELD_TOOL_ID: TOOL_GRIPPER},
        }
    }

    parsed = parse_document(document)

    # The subobject is reported defaulted, which is right — but the fact that MATTERS is what the
    # arm ends up carrying. `extra="forbid"` is what turns the typo into a rejection instead of a
    # dropped key, and without it this arm silently reads as the default tool. The default decides
    # whether CAN id 0x08 is polled, so the assertion is on the tool, not only on the report.
    assert SUBOBJECT_END_EFFECTOR in parsed.defaulted
    assert parsed.document.end_effector.left.tool_id == DEFAULT_TOOL_ID, (
        "a mistyped key must not leave the arm quietly carrying a tool nobody chose"
    )
