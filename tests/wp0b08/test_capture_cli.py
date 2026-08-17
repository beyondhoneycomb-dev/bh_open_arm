"""The acceptance capture's entry point: the rig table, the verdict, and what it refuses.

`PG-CAM-001` goes `SUPERSEDED` on a camera-set change, a rig-profile change or a USB topology
change (`03` §5.9), so the run is not a one-off — it is a thing that gets repeated whenever the
bench moves. A measurement that lives in a scratch file is a measurement nobody can repeat, and
the numbers it produced then become unfalsifiable.

No camera is opened here. What is under test is the part that decides: which slots the rig has,
how each measured number is judged, and whether an unjudged run can report success.
"""

from __future__ import annotations

import json

import pytest

from backend.camera.cli import (
    ACHIEVED_FPS_FLOOR,
    DROP_LIMIT_FRACTION,
    RIG_SLOTS,
    SLOP_LIMIT_MS,
    SlotOutcome,
    capture_verdict,
)

TARGET_FPS = 30.0
WINDOW_S = 600.0


def _healthy(slot: str) -> SlotOutcome:
    """A slot that met every bar with room to spare."""
    return SlotOutcome(
        slot=slot,
        target_fps=TARGET_FPS,
        received=17_900,
        expected=18_001,
        device_skips=180,
        achieved_fps=29.83,
    )


def test_the_rig_table_names_the_three_registered_slots() -> None:
    """The registered set is two wrist cameras and the stereo scene camera."""
    assert set(RIG_SLOTS) == {"wrist_left", "wrist_right", "scene_stereo"}


def test_every_slot_is_bound_by_port_and_not_by_device_node() -> None:
    """The wrist pair shares one serial and device nodes renumber between boots.

    This bench has had the ZED-M and an Arducam swap device numbers while both `bus_info` ports
    stayed put, so a table naming nodes would have been silently wrong about which camera is
    which — and left and right wrist swapped is not visible in the footage.
    """
    for slot, binding in RIG_SLOTS.items():
        assert binding.port_path.startswith("usb-"), slot
        assert "/dev/video" not in binding.port_path, slot


def test_a_run_inside_every_bar_passes() -> None:
    """The positive, so a PASS is not what this function returns for everything."""
    verdict = capture_verdict(
        slots=[_healthy(slot) for slot in RIG_SLOTS],
        pair_q99_ms={("wrist_left", "wrist_right"): 4.0},
        duration_s=WINDOW_S,
    )

    assert verdict.passed
    assert verdict.failures == ()


def test_a_drop_rate_over_the_bar_fails_and_names_the_slot() -> None:
    """`NFR-CAM-003` — the device drop is judged per camera, not against the loop's throughput."""
    over = SlotOutcome(
        slot="scene_stereo",
        target_fps=TARGET_FPS,
        received=17_900,
        expected=18_001,
        device_skips=500,
        achieved_fps=29.83,
    )

    verdict = capture_verdict(
        slots=[_healthy("wrist_left"), over],
        pair_q99_ms={("wrist_left", "scene_stereo"): 4.0},
        duration_s=WINDOW_S,
    )

    assert not verdict.passed
    assert any("scene_stereo" in failure and "drop" in failure for failure in verdict.failures)


def test_an_achieved_rate_under_the_floor_fails() -> None:
    """A camera running below target × 0.95 did not deliver the profile it was asked for."""
    slow = SlotOutcome(
        slot="wrist_left",
        target_fps=TARGET_FPS,
        received=17_000,
        expected=18_001,
        device_skips=100,
        achieved_fps=28.0,
    )

    verdict = capture_verdict(slots=[slow], pair_q99_ms={}, duration_s=WINDOW_S)

    assert not verdict.passed
    assert any("fps" in failure for failure in verdict.failures)


def test_a_pair_over_the_slop_bar_fails_and_says_it_is_at_the_physical_ceiling() -> None:
    """The bar and the maximum possible value are the same number, and that has to be said.

    `03` §5.9 fixes two cameras with no hardware sync at up to half a frame apart — 16.7 ms at
    30 fps — which is exactly the bar `NFR-CAM-002` sets. A pair whose rates differ sweeps the
    whole range, so a long enough run drives its q99 to the ceiling by construction. Reporting
    the breach without that sentence sends the next person hunting a defect in the rig.
    """
    verdict = capture_verdict(
        slots=[_healthy("wrist_left")],
        pair_q99_ms={("scene_stereo", "wrist_left"): 16.9},
        duration_s=WINDOW_S,
    )

    assert not verdict.passed
    breach = next(f for f in verdict.failures if "16.9" in f)
    assert "16.7" in breach
    assert "ceiling" in breach.lower() or "maximum" in breach.lower()


def test_a_run_with_no_pair_measured_is_refused_rather_than_passed() -> None:
    """Acceptance ③ is a pair measurement; a single-camera run cannot answer it.

    Passing here would report a gate met by a run that never took the reading.
    """
    verdict = capture_verdict(slots=[_healthy("wrist_left")], pair_q99_ms={}, duration_s=WINDOW_S)

    assert not verdict.passed
    assert any("pair" in failure for failure in verdict.failures)


def test_a_run_with_no_slots_names_that_as_its_own_breach() -> None:
    """A capture over nothing must say so, not only that it measured no pair.

    Both breaches are asserted because a run with no camera also has no pair, so checking only
    `passed` lets the slot branch be deleted without any test noticing — the pair branch would
    catch every case on its own while naming the wrong cause.
    """
    verdict = capture_verdict(slots=[], pair_q99_ms={}, duration_s=WINDOW_S)

    assert not verdict.passed
    assert any("no slot" in failure for failure in verdict.failures)
    assert any("pair" in failure for failure in verdict.failures)


def test_the_verdict_renders_as_json_a_later_run_can_be_compared_against() -> None:
    """`SUPERSEDED` means this gets re-run; two runs are only comparable if both are readable."""
    verdict = capture_verdict(
        slots=[_healthy(slot) for slot in RIG_SLOTS],
        pair_q99_ms={("wrist_left", "wrist_right"): 4.0},
        duration_s=WINDOW_S,
    )

    document = json.loads(json.dumps(verdict.to_document()))

    assert document["passed"] is True
    assert document["duration_s"] == WINDOW_S
    assert {row["slot"] for row in document["slots"]} == set(RIG_SLOTS)
    assert document["bars"] == {
        "drop_fraction": DROP_LIMIT_FRACTION,
        "achieved_fps_floor": ACHIEVED_FPS_FLOOR,
        "pair_q99_ms": SLOP_LIMIT_MS,
    }


def test_the_bars_are_the_ones_the_gate_document_fixes() -> None:
    """Written out here so the constants are checked against `03` §5.9 rather than themselves."""
    assert DROP_LIMIT_FRACTION == 0.02
    assert ACHIEVED_FPS_FLOOR == 0.95
    assert SLOP_LIMIT_MS == 16.7


def test_the_device_drop_is_computed_from_skips_not_from_the_received_count() -> None:
    """Three independent cameras recorded exactly 17718 frames in the ten-minute run.

    The runner polls slots in one fixed-order pass, so every slot advances at the slowest one's
    rate and the count-based figure reports all three at the worst slot's number. The per-camera
    truth is in each device's own timestamp gaps — 247, 255 and 280 skips, which is 1.37%, 1.42%
    and 1.56%.
    """
    tied = SlotOutcome(
        slot="wrist_left",
        target_fps=TARGET_FPS,
        received=17_718,
        expected=18_001,
        device_skips=247,
        achieved_fps=29.53,
    )

    assert tied.device_drop_fraction == pytest.approx(247 / 18_001)
    assert tied.device_drop_fraction < (18_001 - 17_718) / 18_001
