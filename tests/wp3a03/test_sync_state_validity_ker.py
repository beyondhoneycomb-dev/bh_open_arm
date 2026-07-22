"""WP-3A-03 ④ / ⑤ — sync_state operational rule, three-level validity, zero-CAN KER slot.

`02b` §5.2 WP-3A-03 ④: a non-abstract `sync_state(obs)` exists; the operational GUI
loop must call it (closed-loop IK), while the LeRobot CLI path is verification-only and
open-loop — an operational path without `sync_state` is the `FAIL_BLOCKING` open-loop
defect (`FR-TEL-006`/`007`). ⑤: the reserved KER insertion slot consumes zero CAN
channels (`FR-TEL-062`..`064`). The dual VR timestamps are consumed from `CTR-PRIM`.
"""

from __future__ import annotations

import pytest

import contracts.teleop as tel
from contracts.prim import AGE_INPUT_ROLE, ClockRole


def test_sync_state_method_name_is_declared() -> None:
    """The contract names the non-abstract method the operational loop calls each tick."""
    assert tel.SYNC_STATE_METHOD == "sync_state"


def test_only_the_gui_loop_is_operational() -> None:
    """The GUI loop is operational; the CLI path is verification-only (FR-TEL-007)."""
    assert tel.OperationalPath.GUI_LOOP.is_operational
    assert not tel.OperationalPath.CLI.is_operational


def test_operational_path_without_sync_state_is_the_open_loop_defect() -> None:
    """An operational loop that omits `sync_state` runs IK open-loop — FAIL_BLOCKING."""
    tel.require_sync_state_on_operational(tel.OperationalPath.GUI_LOOP, calls_sync_state=True)
    with pytest.raises(tel.OpenLoopOperationalError):
        tel.require_sync_state_on_operational(tel.OperationalPath.GUI_LOOP, calls_sync_state=False)


def test_cli_verification_path_is_exempt_from_sync_state() -> None:
    """The CLI path is documented open-loop and verification-only, so it is exempt."""
    tel.require_sync_state_on_operational(tel.OperationalPath.CLI, calls_sync_state=False)


def test_validity_is_three_levels_with_the_wire_values() -> None:
    """OK/STALE/INVALID carry the UDP wire values 0/1/2 (05 §2.7)."""
    assert tel.TeleopValidity.OK.value == 0
    assert tel.TeleopValidity.STALE.value == 1
    assert tel.TeleopValidity.INVALID.value == 2


def test_stale_passes_through_and_invalid_stops_publication() -> None:
    """STALE still publishes the last pose; INVALID stops publication (05 §2.14)."""
    assert tel.TeleopValidity.OK.is_publishable
    assert tel.TeleopValidity.STALE.is_publishable
    assert not tel.TeleopValidity.INVALID.is_publishable


def test_non_ok_validity_surfaces_through_the_shared_error_envelope() -> None:
    """STALE and INVALID wrap frozen OA-TEL-* codes; OK has no envelope."""
    stale = tel.validity_envelope(tel.TeleopValidity.STALE)
    invalid = tel.validity_envelope(tel.TeleopValidity.INVALID)
    assert stale is not None and stale.code == "OA-TEL-003"
    assert invalid is not None and invalid.code == "OA-TEL-002"
    assert tel.validity_envelope(tel.TeleopValidity.OK) is None


def test_reserved_ker_slot_consumes_zero_can_channels() -> None:
    """The reserved KER slot is USB, IK-free, and consumes zero CAN channels (FR-TEL-063)."""
    slot = tel.reserved_ker_slot()
    assert slot.transport == "usb"
    assert slot.can_channels == 0
    assert not slot.performs_ik
    assert slot.usb_vid == 0x303A
    assert slot.usb_pid == 0x4002
    tel.verify_ker_consumes_zero_can(slot)


def test_a_ker_slot_that_claims_a_can_channel_is_refused() -> None:
    """A KER slot consuming any CAN channel would change the CAN DAG and is rejected."""
    with pytest.raises(tel.KerContractError):
        tel.KerInsertionSlot(
            transport="usb", usb_vid=0x303A, usb_pid=0x4002, can_channels=1, performs_ik=False
        )


def test_a_ker_slot_that_performs_ik_is_refused() -> None:
    """The KER returns joint angles directly; a slot that performs IK breaks the contract."""
    with pytest.raises(tel.KerContractError):
        tel.KerInsertionSlot(
            transport="usb", usb_vid=0x303A, usb_pid=0x4002, can_channels=0, performs_ik=True
        )


def test_dual_timestamp_roles_are_consumed_from_ctr_prim() -> None:
    """The VR source `t` is the CLIENT age input; the PC receive instant is the SERVER clock."""
    assert tel.SOURCE_TS_ROLE == ClockRole.CLIENT == AGE_INPUT_ROLE
    assert tel.RECEIVE_TS_ROLE == ClockRole.SERVER
    tel.verify_source_is_age_input(ClockRole.CLIENT)
    with pytest.raises(ValueError, match="age input"):
        tel.verify_source_is_age_input(ClockRole.SERVER)


def test_teleop_sample_preserves_both_timestamps() -> None:
    """A received sample keeps the source time and the server receive instant (WP-3B-07)."""
    sample = tel.TeleopSample(
        source_ts=1234.5, receive_mono_ns=987_654_321, validity=tel.TeleopValidity.OK
    )
    assert sample.source_ts == 1234.5
    assert sample.receive_mono_ns == 987_654_321
    with pytest.raises(ValueError, match="int ns"):
        tel.TeleopSample(source_ts=1.0, receive_mono_ns=1.5, validity=tel.TeleopValidity.OK)  # type: ignore[arg-type]
