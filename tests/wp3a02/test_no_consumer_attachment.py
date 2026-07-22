"""WP-3A-02 ① — capture_ts is attached at grab; a consumer stamping receive time fails.

`02b` §5.2 WP-3A-02 ① makes consumer-side timestamp attachment a build-blocking
defect: a GUI or recorder that writes a `<slot>_capture_ts` cell, or builds a
`CaptureTimestamp`, from a live clock read has recorded receive time under the
capture column, and the exposure phase difference is lost for good. The 3B
consumers do not exist yet, so the ban is proven here on synthetic consumer
modules — ones that stamp receive time (must fire) and ones that only read the
sidecar (must stay silent). The second half proves the timestamp domain is
*consumed* from CTR-PRIM: a CAP that restates it is caught by the no-redefinition
scan, and this contract's own tree restates nothing.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

import contracts.capture as cap
from contracts.prim import check_no_redefinition

CAPTURE_TREE = Path(__file__).resolve().parents[2] / "contracts" / "capture"


def _write(path: Path, source: str) -> Path:
    """Write a synthetic consumer module and return its path."""
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


# --- ① consumer-side attachment fires ---------------------------------------


def test_gui_stamping_receive_time_into_a_sidecar_cell_fires(tmp_path: Path) -> None:
    """A GUI writing `<slot>_capture_ts` from a monotonic clock read is refused."""
    gui = _write(
        tmp_path / "gui.py",
        """
        import time

        def on_frame(row, frame):
            # Receive-time stamp wearing the capture column's name.
            row["left_wrist_capture_ts"] = time.monotonic_ns()
        """,
    )
    hits = cap.check_no_consumer_attachment([gui])
    assert [(h.sink, h.clock_call) for h in hits] == [("left_wrist_capture_ts", "monotonic_ns")]


def test_recorder_building_capture_timestamp_from_a_clock_fires(tmp_path: Path) -> None:
    """A recorder constructing CaptureTimestamp from a receive clock is refused."""
    recorder = _write(
        tmp_path / "recorder.py",
        """
        import time
        from contracts.prim import CaptureTimestamp

        def record(frame):
            return CaptureTimestamp(mono_ns=time.perf_counter_ns())
        """,
    )
    hits = cap.check_no_consumer_attachment([recorder])
    assert any(h.clock_call == "perf_counter_ns" for h in hits)


def test_attribute_sink_from_a_wall_clock_fires(tmp_path: Path) -> None:
    """Stamping a `self.capture_ts` attribute from a wall clock is receive-time too."""
    module = _write(
        tmp_path / "sink.py",
        """
        import time

        class Sink:
            def store(self, frame):
                self.capture_ts = time.time_ns()
        """,
    )
    hits = cap.check_no_consumer_attachment([module])
    assert [(h.sink, h.clock_call) for h in hits] == [("capture_ts", "time_ns")]


# --- consumers that only read the sidecar stay silent ------------------------


def test_consumer_reading_the_sidecar_column_is_silent(tmp_path: Path) -> None:
    """Reading a capture-ts column, or building from a device grab time, is clean."""
    good = _write(
        tmp_path / "reader.py",
        """
        from contracts.prim import CaptureTimestamp, slot_from_capture_ts_column

        def load(row, slot):
            column = slot.capture_ts_column()
            return CaptureTimestamp(mono_ns=row[column])

        def from_device(frame):
            # The device supplied the grab instant; no clock is read here.
            return CaptureTimestamp(mono_ns=frame.grab_mono_ns)
        """,
    )
    assert cap.check_no_consumer_attachment([good]) == []


def test_assigning_the_join_column_is_not_an_attachment(tmp_path: Path) -> None:
    """`frame_index` is the join key, not a capture instant; assigning it is clean."""
    module = _write(
        tmp_path / "join.py",
        """
        import time

        def build(row, index):
            row["frame_index"] = index
            row["seq"] = time.monotonic_ns()
        """,
    )
    assert cap.check_no_consumer_attachment([module]) == []


# --- ② (WP-3A-00) the timestamp domain is consumed, not redefined ------------


def test_cap_redefining_the_timestamp_domain_is_caught_statically(tmp_path: Path) -> None:
    """The named WP-3A-00 example: a CAP restating the timestamp domain must fail."""
    forked = _write(
        tmp_path / "cap_fork.py",
        """
        from contracts.prim import CameraSlotKey

        # CAP forking the timestamp primitive instead of importing it.
        CLOCK_SOURCE = "CLOCK_REALTIME"

        class CaptureTimestamp:
            def __init__(self, wall_ns):
                self.wall_ns = wall_ns
        """,
    )
    hits = check_no_redefinition([forked])
    assert {h.symbol for h in hits} == {"CLOCK_SOURCE", "CaptureTimestamp"}


def test_this_contract_redefines_no_primitive() -> None:
    """The real CTR-CAP tree consumes every primitive and restates none."""
    tree = sorted(CAPTURE_TREE.glob("*.py"))
    assert tree, "the capture contract tree has no modules to scan"
    assert check_no_redefinition(tree) == []


def test_verify_attachment_site_pins_the_grab_site() -> None:
    """The runtime twin refuses any attachment site other than grab."""
    cap.verify_attachment_site(cap.AttachmentSite.GRAB)
    with pytest.raises(cap.CaptureContractError):
        cap.verify_attachment_site(cap.AttachmentSite.RECEIVE)
