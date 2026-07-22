"""CTR-PRIM@v1 primitive behaviour: single definition point, join, and re-export.

Covers the acceptance items WP-3A-00 can prove at the primitive level (`02b`
§5.2): ① each primitive has one definition point, ④ the camera identifier joins
across CAM/CAP/WS/REC with one grammar, and the row-4/row-6 re-export identity
(the action shape is CTR-ACT@v1's, the error envelope wraps CTR-ERR@v1) so no
consumer restates them. The JSON mirror is checked against the Python surface so
"single definition point" holds across the two frozen bodies, not just within one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import contracts.prim as prim
from contracts.action import BIMANUAL_ACTION_DIM as ACT_BIMANUAL
from contracts.action import CONTRACT_ID as ACT_CONTRACT_ID
from contracts.action import SINGLE_ARM_ACTION_DIM as ACT_SINGLE
from contracts.action import AcceptedPositionAction as ActAccepted
from contracts.errors import CONTRACT_ID as ERR_CONTRACT_ID
from contracts.errors import Severity as ErrSeverity
from contracts.errors import codes as err_codes
from contracts.units import Deg as UnitDeg

SCHEMA_JSON = Path(__file__).resolve().parents[2] / "contracts" / "prim" / "schema.json"


def _json() -> dict:
    """Load the frozen JSON mirror."""
    return json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))


# --- ① single definition point / re-export identity -------------------------


def test_action_shape_is_ctr_act_not_restated() -> None:
    """The action payload primitive IS CTR-ACT@v1's shape, re-exported, not a copy."""
    assert prim.SINGLE_ARM_ACTION_DIM is ACT_SINGLE == 8
    assert prim.BIMANUAL_ACTION_DIM is ACT_BIMANUAL == 16
    assert prim.AcceptedPositionAction is ActAccepted
    assert prim.Deg is UnitDeg
    assert prim.ACTION_CONTRACT_ID == ACT_CONTRACT_ID
    assert prim.ACTION_IS_POSITION_ONLY is True


def test_error_envelope_wraps_ctr_err_not_restated() -> None:
    """The error envelope primitive re-exports CTR-ERR@v1's severity and code registry."""
    assert prim.Severity is ErrSeverity
    assert prim.codes is err_codes
    assert prim.ERROR_CONTRACT_ID == ERR_CONTRACT_ID


def test_consumed_contracts_are_the_frozen_upstreams() -> None:
    """The primitives consume exactly the three 0-A/0-Ops contracts by reference."""
    assert set(prim.CONSUMED_CONTRACTS) == {"CTR-ACT@v1", "CTR-ERR@v1", "CTR-UNIT@v1"}


# --- ④ camera identifier round-trip-joins across CAM/CAP/WS/REC --------------


@pytest.mark.parametrize(
    "slot",
    [
        prim.arm_slot("left", "wrist"),
        prim.arm_slot("right", "wrist"),
        prim.CameraSlotKey("scene"),
        prim.sim_slot("scene"),
    ],
)
def test_camera_identifier_round_trip_joins(slot: prim.CameraSlotKey) -> None:
    """One slot renders into each contract's surface and parses back to the same slot.

    CAM holds the key itself, CAP names a `<slot>_capture_ts` column, WS tags a
    binary frame `<slot>:<channel>`, and REC keys `observation.images.<slot>`. All
    four must recover the identical `CameraSlotKey`, or the four surfaces do not join.
    """
    cam = slot  # CAM registry key is the slot itself
    cap = prim.slot_from_capture_ts_column(slot.capture_ts_column())
    ws = prim.slot_from_ws_tag(slot.ws_tag(prim.FrameType.RGB))
    rec = prim.slot_from_image_key(slot.image_key())
    assert cam == cap == ws == rec == slot


def test_arm_prefix_is_part_of_the_key() -> None:
    """The `left_`/`right_` prefix is auto-attached and recoverable from the key."""
    left = prim.arm_slot("left", "wrist")
    assert left.value == "left_wrist"
    assert left.arm == "left"
    assert prim.arm_slot("right", "wrist").arm == "right"
    assert prim.CameraSlotKey("scene").arm is None


def test_sim_camera_is_a_separate_namespace() -> None:
    """A sim scene camera lives under the sim namespace and reads as sim."""
    sim = prim.sim_slot("scene")
    assert sim.value == "sim_scene"
    assert sim.is_sim is True
    assert prim.CameraSlotKey("scene").is_sim is False


def test_bad_slot_key_is_refused() -> None:
    """A key outside the one grammar is a primitive redefinition, not a new camera."""
    for bad in ("Left_Wrist", "left wrist", "1cam", "left/wrist", ""):
        with pytest.raises(prim.PrimitiveRedefinitionError):
            prim.CameraSlotKey(bad)


def test_double_prefix_is_refused() -> None:
    """Passing an already-namespaced base to a constructor forks the identifier."""
    with pytest.raises(prim.PrimitiveRedefinitionError):
        prim.arm_slot("left", "left_wrist")
    with pytest.raises(prim.PrimitiveRedefinitionError):
        prim.sim_slot("sim_scene")


# --- error envelope, frame type, queue semantics ----------------------------


def test_error_envelope_requires_a_registered_code() -> None:
    """The envelope wraps a real OA-* code and refuses a malformed one."""
    code = next(iter(prim.REGISTRY.codes.values()))
    envelope = prim.error_envelope(code, "bus dropped")
    assert envelope.code == code.code
    assert envelope.severity == code.severity
    with pytest.raises(prim.PrimitiveRedefinitionError):
        prim.ErrorEnvelope(code="not-a-code", reason="x", severity=prim.Severity.ERROR)


def test_frame_type_rgb_required_depth_optional() -> None:
    """RGB is the required capability floor; depth is optional, single-channel uint16."""
    assert prim.REQUIRED_FRAME_TYPE == prim.FrameType.RGB
    assert prim.OPTIONAL_FRAME_TYPES == (prim.FrameType.DEPTH,)
    assert prim.FRAME_TYPE_CHANNELS[prim.FrameType.DEPTH] == 1
    assert prim.FRAME_TYPE_DTYPE[prim.FrameType.DEPTH] == "uint16"


def test_every_queue_class_is_bounded_and_lease_outranks() -> None:
    """Queues are bounded; the lease class is the highest priority and a drop is a defect."""
    for profile in prim.QUEUE_PROFILES.values():
        assert profile.bounded_capacity > 0
    lease = prim.QUEUE_PROFILES["lease"]
    assert lease.priority == prim.PriorityClass.LEASE
    assert min(p.priority for p in prim.QUEUE_PROFILES.values()) == prim.PriorityClass.LEASE
    assert lease.drop_classification == prim.DropClassification.DEFECT
    assert (
        prim.QUEUE_PROFILES["camera_preview"].drop_classification == prim.DropClassification.NORMAL
    )


def test_unbounded_queue_is_refused() -> None:
    """An unbounded queue class contradicts the primitive and is refused."""
    with pytest.raises(prim.PrimitiveRedefinitionError):
        prim.QueueSemantics(
            name="bad",
            bounded_capacity=0,
            priority=prim.PriorityClass.CAMERA,
            drop_policy=prim.DropPolicy.LATEST_WINS,
            drop_classification=prim.DropClassification.NORMAL,
        )


# --- JSON mirror agrees with the Python surface (single definition point) ----


def test_json_mirror_agrees_with_python_surface() -> None:
    """The two frozen bodies declare one contract: the JSON must not diverge from Python."""
    doc = _json()
    assert doc["contract"] == prim.CONTRACT_ID
    assert doc["schema_version"] == prim.SCHEMA_VERSION
    assert set(doc["consumed_contracts"]) == set(prim.CONSUMED_CONTRACTS)

    cam = doc["primitives"]["camera_identifier"]
    assert cam["slot_key_pattern"] == prim.CAMERA_SLOT_KEY_PATTERN.pattern
    assert cam["arm_prefixes"] == prim.ARM_PREFIXES
    assert cam["sim_namespace_prefix"] == prim.SIM_NAMESPACE_PREFIX

    clock = doc["primitives"]["timestamp_domain"]
    assert clock["clock_source"] == prim.CLOCK_SOURCE
    assert clock["expiry_judge_role"] == prim.EXPIRY_JUDGE_ROLE.value
    assert clock["age_input_role"] == prim.AGE_INPUT_ROLE.value
    assert clock["lease_expiry_field"] == prim.LEASE_EXPIRY_FIELD
    assert clock["lease_issued_field"] == prim.LEASE_ISSUED_FIELD

    frame = doc["primitives"]["frame_type"]
    assert frame["required"] == prim.REQUIRED_FRAME_TYPE.value
    assert frame["channels"] == {ft.value: n for ft, n in prim.FRAME_TYPE_CHANNELS.items()}

    action = doc["primitives"]["action_payload"]
    assert action["single_arm_dim"] == prim.SINGLE_ARM_ACTION_DIM
    assert action["bimanual_dim"] == prim.BIMANUAL_ACTION_DIM
    assert action["position_only"] is prim.ACTION_IS_POSITION_ONLY

    queues = doc["primitives"]["queue_semantics"]["profiles"]
    assert set(queues) == set(prim.QUEUE_PROFILES)
    for name, spec in queues.items():
        profile = prim.QUEUE_PROFILES[name]
        assert spec["bounded_capacity"] == profile.bounded_capacity
        assert spec["drop_policy"] == profile.drop_policy.value
        assert spec["drop_classification"] == profile.drop_classification.value

    envelope = doc["primitives"]["error_envelope"]
    assert envelope["code_pattern"] == prim.ERROR_CODE_PATTERN.pattern
    assert envelope["wraps"] == prim.ERROR_CONTRACT_ID
