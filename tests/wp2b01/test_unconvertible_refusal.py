"""Acceptance (3) — unconvertible items are load-refused with a stated reason.

Three items have no v2 representation and so cannot be carried across (spec 12 §2.6): a link7
inertia (the wrist-end mass moved into the end-effector, v2 has no link7 body), the base_link
inertia (v2 re-expresses it in a rotated frame), and any gripper/finger model (v2 defines no
finger dynamics). An asset carrying one is refused, and the refusal names the item and the
reason rather than converting it into a silent error.
"""

from __future__ import annotations

import pytest

from backend.dynamics.asset import convert_v1_to_v2, unconvertible_items
from backend.dynamics.converter import JointFrameConverter
from backend.dynamics.errors import DynamicsConversionError
from tests.wp2b01.conftest import make_v1_asset, make_v2_provenance


def test_link7_inertia_is_unconvertible(default_converter: JointFrameConverter) -> None:
    """A v1 link7 inertia is refused: v2 has no link7 body to receive it."""
    asset = make_v1_asset(inertials={"link3": {}, "link7": {"mass": 0.4659771327380578}})
    items = unconvertible_items(asset)
    assert [item.item for item in items] == ["link7"]
    assert "no link7 body" in items[0].reason
    with pytest.raises(DynamicsConversionError, match="link7"):
        convert_v1_to_v2(asset, default_converter, make_v2_provenance())


def test_base_link_rotated_frame_is_unconvertible(
    default_converter: JointFrameConverter,
) -> None:
    """A v1 base_link inertia is refused: v2 re-expresses it in a rotated frame."""
    asset = make_v1_asset(inertials={"base_link": {"origin_z": 0.0308}})
    items = unconvertible_items(asset)
    assert [item.item for item in items] == ["base_link"]
    assert "rotated frame" in items[0].reason
    with pytest.raises(DynamicsConversionError, match="base_link"):
        convert_v1_to_v2(asset, default_converter, make_v2_provenance())


def test_gripper_model_is_unconvertible(default_converter: JointFrameConverter) -> None:
    """A v1 gripper model is refused: v2 defines no finger dynamics."""
    asset = make_v1_asset(gripper_model={"finger_stiffness": 1.0})
    items = unconvertible_items(asset)
    assert [item.item for item in items] == ["gripper_model"]
    assert "no gripper/finger dynamics" in items[0].reason
    with pytest.raises(DynamicsConversionError, match="gripper_model"):
        convert_v1_to_v2(asset, default_converter, make_v2_provenance())


def test_every_unconvertible_item_is_named_at_once(
    default_converter: JointFrameConverter,
) -> None:
    """All unconvertible items are reported together, not one refusal at a time."""
    asset = make_v1_asset(
        inertials={"link7": {}, "base_link": {}, "link3": {}},
        gripper_model={"x": 1},
    )
    items = {item.item for item in unconvertible_items(asset)}
    assert items == {"link7", "base_link", "gripper_model"}
    with pytest.raises(DynamicsConversionError, match="3 unconvertible item"):
        convert_v1_to_v2(asset, default_converter, make_v2_provenance())


def test_convertible_asset_is_promoted_to_v2(
    default_converter: JointFrameConverter,
) -> None:
    """An asset with only convertible links converts, is re-stamped v2, and passes the gate."""
    converted = convert_v1_to_v2(make_v1_asset(), default_converter, make_v2_provenance())
    assert converted.provenance.robot_version == "2.0"
    assert converted.warnings == ()
    # The seed pose was rewritten into the v2 frame: joint2 carries the +pi/2 shift.
    assert converted.payload["seed_pose_rad"][1] == pytest.approx(1.5707963267948966)
