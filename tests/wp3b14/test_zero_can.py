"""WP-3B-14 acceptance ③ (zero CAN) — the KER consumes no CAN channel.

The KER is USB, so inserting it must not touch the CAN DAG (FR-TEL-063). Proven three
ways: the frozen reserved slot pins `can_channels` to zero; no CAN symbol appears in
the package source (static scan); and a full mock teleoperator lifecycle runs without
any CAN import or symbol.
"""

from __future__ import annotations

from pathlib import Path

from backend.teleop.ker import (
    RULE_CAN_SYMBOL,
    MockKerDevice,
    OpenArmKER,
    OpenArmKERConfig,
    check_package,
    check_source,
)
from contracts.teleop import (
    KER_CAN_CHANNELS,
    KerContractError,
    KerInsertionSlot,
    TeleopValidity,
    reserved_ker_slot,
    verify_ker_consumes_zero_can,
)

_KER_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "backend" / "teleop" / "ker"


def test_reserved_slot_consumes_zero_can_channels() -> None:
    """The frozen KER slot the plugin fills consumes zero CAN channels."""
    slot = reserved_ker_slot()
    assert slot.can_channels == KER_CAN_CHANNELS == 0
    verify_ker_consumes_zero_can(slot)


def test_teleoperator_reports_a_zero_can_insertion_slot() -> None:
    """The teleoperator's own insertion slot verifies as zero-CAN at runtime."""
    teleop = OpenArmKER(OpenArmKERConfig())
    verify_ker_consumes_zero_can(teleop.insertion_slot())
    assert teleop.insertion_slot().can_channels == 0


def test_a_slot_claiming_a_can_channel_is_refused() -> None:
    """A KER slot that consumes any CAN channel breaks the contract (would change DAG)."""
    try:
        KerInsertionSlot(
            transport="usb", usb_vid=0x303A, usb_pid=0x4002, can_channels=1, performs_ik=False
        )
    except KerContractError:
        return
    raise AssertionError("a CAN-claiming KER slot must be refused")


def test_package_source_has_no_can_symbol() -> None:
    """No CAN symbol appears anywhere in the KER package (static half)."""
    can_violations = [v for v in check_package(_KER_PACKAGE_ROOT) if v.rule == RULE_CAN_SYMBOL]
    assert can_violations == []


def test_can_ban_is_not_vacuous() -> None:
    """A CAN import or constant trips the CAN ban."""
    for source in ("import can\n", "s = socket(AF_CAN, 0)\n", "import can.interface\n"):
        assert any(v.rule == RULE_CAN_SYMBOL for v in check_source(source))


def test_full_mock_lifecycle_touches_no_can() -> None:
    """Construct, connect, act, and disconnect the KER without any CAN symbol executing."""
    teleop = OpenArmKER(OpenArmKERConfig(bimanual=True))
    teleop.device = MockKerDevice.constant(tuple(0.0 for _ in range(16)), TeleopValidity.OK)
    teleop.connect()
    for _ in range(5):
        teleop.get_action()
    teleop.disconnect()
    lifecycle_can = [v for v in check_package(_KER_PACKAGE_ROOT) if v.rule == RULE_CAN_SYMBOL]
    assert lifecycle_can == []
