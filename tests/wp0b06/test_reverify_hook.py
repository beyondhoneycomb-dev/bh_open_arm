"""Acceptance §4.1 — the real-fixture re-verification hook.

The parse chain runs on synthetic fixtures throughout this suite. What is deferred
is the claim that it matches a *real* adapter's `lsusb -t`, a *real* `ip -s -d`
dump, and a *real* `motor_sampling_check` log. The hook is the required deferral
artifact: `test_hook_reruns_parse_chain_over_a_capture_dir` drives it over a
capture directory built here, proving it re-verifies rather than being a stub, and
`test_real_hardware_reverify` skips until `OPENARM_USB_REAL_FIXTURE` names a rig
capture, at which point the identical chain runs against the real bytes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ops.hw.usb.frames import FrameVerdict
from ops.hw.usb.reverify import fixture_dir_from_env, reverify_from_fixture

_FIXTURES = Path(__file__).parent / "fixtures"


def _build_capture_dir(dest: Path) -> None:
    """Assemble a capture directory in the layout the hook expects."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "lsusb_t.txt").write_text(
        (_FIXTURES / "lsusb_t_shared_controller.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (dest / "ip_s_d_can0.txt").write_text(
        (_FIXTURES / "ip_s_d_can0.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (dest / "msc_can0_500.log").write_text(
        (_FIXTURES / "msc_can0_500.log").read_text(encoding="utf-8"), encoding="utf-8"
    )


def test_hook_reruns_parse_chain_over_a_capture_dir(tmp_path: Path) -> None:
    """The hook re-derives topology, bus stats, f_max and frames from a capture dir."""
    capture = tmp_path / "capture"
    _build_capture_dir(capture)

    result = reverify_from_fixture(capture)

    assert result.topology is not None
    assert result.topology.shared_controller is True
    assert len(result.bus_stats) == 1
    assert result.bus_stats[0].restarts == 2
    assert len(result.fmax_per_arm) == 1
    assert result.fmax_per_arm[0].iface == "can0"
    assert result.fmax_per_arm[0].f_max_hz == 500
    assert result.frames.verdict is FrameVerdict.PATTERN_B_NORMAL


def test_hook_tolerates_a_missing_topology_capture(tmp_path: Path) -> None:
    """A capture dir without lsusb output still re-verifies what it has."""
    capture = tmp_path / "partial"
    capture.mkdir()
    (capture / "ip_s_d_can0.txt").write_text(
        (_FIXTURES / "ip_s_d_can0.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    result = reverify_from_fixture(capture)
    assert result.topology is None
    assert len(result.bus_stats) == 1


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason=(
        "deferred: needs a real rig capture; set OPENARM_USB_REAL_FIXTURE to a "
        "directory of captured lsusb_t.txt / ip_s_d_<iface>.txt / msc_<iface>_<hz>.log"
    ),
)
def test_real_hardware_reverify() -> None:
    """Re-verify against a real rig capture the moment one is supplied.

    The verdicts, not their containers. `TopologyReport` and `CanBusStats` are returned for
    any input the parsers accept, including input they found nothing in: a topology that
    located no adapter still reports `shared_controller=None` and `all_high_speed_usb2=False`,
    and bus stats whose counter row did not match still carry `None` in every counter field.
    Those are the answers acceptances ② ④ ⑥ are made of, so a capture that parsed to empty
    satisfies an existence check while leaving all three unmeasured.
    """
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    result = reverify_from_fixture(fixture_dir)

    assert result.topology is not None or result.bus_stats, (
        f"nothing in {fixture_dir} parsed: no lsusb_t.txt and no ip_s_d_<iface>.txt"
    )

    if result.topology is not None:
        # ② and ⑥ are both statements about the adapters. With none located there is no
        # controller to share and no link speed to record, and the report says so in fields
        # that read as ordinary negatives.
        assert result.topology.adapters, (
            "the real lsusb -t parsed but located no CAN adapter, so the controller-sharing "
            "and USB-2.0 link-speed acceptances have nothing to judge"
        )

    for stats in result.bus_stats:
        # ④ records the error counters beside the rate, as the independent evidence that a
        # high achieved rate was not bought with a rising error rate. Absent counters make
        # that evidence silently empty.
        assert stats.restarts is not None, f"{stats.iface}: no restart counter parsed"
        assert stats.bus_errors is not None, f"{stats.iface}: no bus-error counter parsed"
        assert stats.error_warn is not None, f"{stats.iface}: no error-warning counter parsed"
        assert stats.error_pass is not None, f"{stats.iface}: no error-passive counter parsed"
        assert stats.bus_off is not None, f"{stats.iface}: no bus-off counter parsed"
