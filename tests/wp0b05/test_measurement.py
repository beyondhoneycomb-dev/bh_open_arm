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


def test_single_channel_does_not_prove_dev_id_separation() -> None:
    """One channel of an adapter cannot exhibit separation, so ③ refuses to claim it.

    The mirror of `test_single_channel_does_not_prove_serial_sharing`, and the gap that let a
    one-channel capture clear the real-capture acceptance: with one entry nothing is absent and
    nothing collides, so a bare uniqueness test is vacuously true. What ③ asserts is that
    `dev_id` separates an adapter's channels, and separation needs two of them to be seen.
    """
    table = build_measurement_table(
        (parse_udevadm_info((_FIXTURES / "can0_serial.txt").read_text(encoding="utf-8")),)
    )

    assert dev_id_distinguishes_channels(table) is False


def test_two_adapters_of_one_channel_each_do_not_prove_dev_id_separation() -> None:
    """Counting interfaces is not the guard; the requirement is per adapter.

    Two dumps from two different adapters, each holding one channel, is two interfaces and
    still no adapter whose channels were separated. A repair that only demanded two entries
    would admit exactly this.
    """
    table = build_measurement_table(
        (
            parse_udevadm_info((_FIXTURES / "can0_serial.txt").read_text(encoding="utf-8")),
            parse_udevadm_info((_FIXTURES / "can2_serial.txt").read_text(encoding="utf-8")),
        )
    )

    assert dev_id_distinguishes_channels(table) is False


def test_a_serialless_adapter_cannot_answer_the_serial_sharing_claim() -> None:
    """Two channels of an adapter that publishes no iSerial settle ③ and leave ② unmeasured.

    Both channels group under one adapter key, so ③ — dev_id splits the channels — is a real
    measurement. ② is not: there is no serial anywhere below the root hub to be shared, so the
    claim has nothing to hold on and the answer must be False rather than a serial borrowed
    from the host controller. The two verdicts differing on the same dumps is the point.
    """
    table = build_measurement_table(
        tuple(
            parse_udevadm_info((_FIXTURES / name).read_text(encoding="utf-8"))
            for name in ("can0_peak_hub_serial.txt", "can1_peak_hub_serial.txt")
        )
    )
    assert set(table.by_adapter()) == {"3-10.3.1.2:1.0"}
    assert dev_id_distinguishes_channels(table) is True
    assert serial_shared_per_adapter(table) is False
