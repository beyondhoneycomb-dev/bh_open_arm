"""The reboot-determinism evaluator (acceptance ⑤ scaffold).

The ten-reboot loop is the observation point (SHAPE-MS) and needs real hardware — it
is deferred. What runs here is the evaluator that judges the captured observations, so a
drift or a short run cannot pass silently once real captures arrive.
"""

from __future__ import annotations

import json
from pathlib import Path

from ops.hw.udev.determinism import (
    REQUIRED_REBOOT_CYCLES,
    RebootObservation,
    evaluate_determinism,
    physical_channel_key,
)
from ops.hw.udev.parser import parse_udevadm_info

_REBOOTS = Path(__file__).resolve().parent / "fixtures" / "reboots"
_UDEVADM = Path(__file__).resolve().parent / "fixtures" / "udevadm"


def _load(name: str) -> tuple[RebootObservation, ...]:
    raw = json.loads((_REBOOTS / name).read_text(encoding="utf-8"))
    return tuple(
        RebootObservation(reboot_index=item["reboot_index"], bindings=item["bindings"])
        for item in raw
    )


def test_ten_identical_reboots_are_stable() -> None:
    """Acceptance ⑤ (evaluator): ten reboots binding the same channels → stable."""
    result = evaluate_determinism(_load("stable.json"), REQUIRED_REBOOT_CYCLES)
    assert result.stable is True
    assert result.cycles_seen == 10
    assert result.drifts == ()


def test_a_swapped_channel_is_caught_as_drift() -> None:
    """A single boot where two names swap channels is flagged — the evaluator bites."""
    result = evaluate_determinism(_load("drift.json"), REQUIRED_REBOOT_CYCLES)
    assert result.stable is False
    assert any("oa_fl" in drift for drift in result.drifts)


def test_short_run_is_not_stable_even_if_consistent() -> None:
    """Fewer than the required cycles cannot pass, however consistent they are."""
    short = _load("stable.json")[:3]
    result = evaluate_determinism(short, REQUIRED_REBOOT_CYCLES)
    assert result.stable is False
    assert result.cycles_seen == 3


def test_physical_channel_key_is_boot_stable_pair() -> None:
    """The key is (adapter, dev_id), never the volatile canN name."""
    interface = parse_udevadm_info((_UDEVADM / "can0_serial.txt").read_text(encoding="utf-8"))
    key = physical_channel_key(interface)
    assert "OA_ADAPTER_A" in key
    assert "0x0" in key
    assert "can0" not in key
