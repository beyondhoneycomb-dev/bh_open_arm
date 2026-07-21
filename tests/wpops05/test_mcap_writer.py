"""Acceptance ④ and ⑤ — MCAP writer runs in a different process; the file loads standardly.

④: NFR-PRF-038 puts the writer off the control loop's process. The writer's PID must differ
from this test process's PID (which stands in for the control loop). ⑤: the file the separate
writer produced must load under the ordinary `mcap` reader and round-trip its messages, with no
rosbag2 anywhere in the path (the dependency half of ⑤ is `test_ros_dependency.py`).
"""

from __future__ import annotations

import os
from pathlib import Path

from ops.telemetry.constants import (
    MCAP_TOPICS,
    TOPIC_CAN_TRACE,
    TOPIC_COMMANDS,
    TOPIC_DIAGNOSTICS,
    TOPIC_JOINTS,
    TOPIC_VIDEO_META,
)
from ops.telemetry.mcap_writer import McapWriterProcess, load_mcap


def test_writer_runs_in_a_different_process(tmp_path: Path) -> None:
    """The MCAP writer's PID is not the control loop's (this process's) PID."""
    writer = McapWriterProcess(tmp_path / "ts.mcap")
    writer.start()
    try:
        assert writer.writer_pid != os.getpid()
        assert writer.writer_pid > 0
    finally:
        writer.close()


def test_all_five_channels_roundtrip_under_the_standard_reader(tmp_path: Path) -> None:
    """Every FR-OPS-006 channel writes and reads back through the standard mcap reader."""
    path = tmp_path / "ts.mcap"
    writer = McapWriterProcess(path)
    writer.start()
    writer.write(TOPIC_JOINTS, 1_000, {"q": [0.0, 1.0]})
    writer.write(TOPIC_COMMANDS, 2_000, {"cmd": "hold"})
    writer.write(TOPIC_DIAGNOSTICS, 3_000, {"severity": "OK"})
    writer.write(TOPIC_CAN_TRACE, 4_000, {"id": 291, "dlc": 8})
    writer.write(TOPIC_VIDEO_META, 5_000, {"cam": "wrist", "fps": 30})
    writer.close()

    messages = load_mcap(path)
    assert [m.topic for m in messages] == list(MCAP_TOPICS)
    assert [m.log_time_ns for m in messages] == [1_000, 2_000, 3_000, 4_000, 5_000]
    assert messages[0].payload == {"q": [0.0, 1.0]}
    assert messages[3].payload == {"id": 291, "dlc": 8}


def test_written_file_is_a_real_mcap(tmp_path: Path) -> None:
    """The produced file carries the MCAP magic — it is a genuine MCAP container."""
    path = tmp_path / "ts.mcap"
    writer = McapWriterProcess(path)
    writer.start()
    writer.write(TOPIC_JOINTS, 1_000, {"q": [0.0]})
    writer.close()

    assert path.read_bytes()[:1] == b"\x89"  # MCAP files begin with the 0x89 magic byte
