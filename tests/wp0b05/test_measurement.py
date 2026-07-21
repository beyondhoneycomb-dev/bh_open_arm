"""The measurement table answers FR-SYS-008's two empirical claims (②③) on fixtures.

The computation runs here; the *real* four-entry measurement needs two adapters and
is deferred (see test_hardware_deferred). The reverify hook re-runs this same table on
a real capture when supplied.
"""

from __future__ import annotations

from pathlib import Path

from ops.hw.udev.measurement import (
    build_measurement_table,
    dev_id_distinguishes_channels,
    serial_shared_per_adapter,
)
from ops.hw.udev.parser import parse_udevadm_info

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "udevadm"

_FOUR_ENTRY = ("can0_serial.txt", "can1_serial.txt", "can2_serial.txt", "can3_serial.txt")


def test_serial_shared_per_adapter_holds_on_four_entry_rig() -> None:
    """Acceptance ② (computed): each adapter's serial is shared across its two channels."""
    table = build_measurement_table(
        tuple(
            parse_udevadm_info((_FIXTURES / name).read_text(encoding="utf-8"))
            for name in _FOUR_ENTRY
        )
    )
    assert serial_shared_per_adapter(table) is True
    groups = table.by_adapter()
    assert set(groups) == {"OA_ADAPTER_A", "OA_ADAPTER_B"}
    assert all(len(entries) == 2 for entries in groups.values())


def test_dev_id_distinguishes_channels_within_each_adapter() -> None:
    """Acceptance ③ (computed): dev_id is unique per channel inside an adapter."""
    table = build_measurement_table(
        tuple(
            parse_udevadm_info((_FIXTURES / name).read_text(encoding="utf-8"))
            for name in _FOUR_ENTRY
        )
    )
    assert dev_id_distinguishes_channels(table) is True


def test_single_channel_does_not_prove_serial_sharing() -> None:
    """One channel of an adapter cannot exhibit sharing — the check refuses to over-claim."""
    table = build_measurement_table(
        (parse_udevadm_info((_FIXTURES / "can0_serial.txt").read_text(encoding="utf-8")),)
    )
    assert serial_shared_per_adapter(table) is False
