"""The writer's failure path — a dead writer must be loud, bounded, and non-blocking.

NFR-PRF-038 moves the MCAP writer off the control loop's process. That boundary is a
place a partner can die without saying so: the child owns the file, and if `open()` fails
(missing directory, permissions, a full disk) it exits while the control loop keeps
handing it samples. Nothing in the hand-off notices on its own.

Three properties are pinned here, one per failure the boundary can produce: the control
loop is never blocked by telemetry, the loss is counted rather than assumed, and the
session boundary refuses to report a file as written when it is not.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ops.telemetry.constants import MCAP_QUEUE_MAX_ITEMS, TOPIC_JOINTS
from ops.telemetry.mcap_writer import McapWriterError, McapWriterProcess

# Long enough for the child to reach `open()` and exit; the assertions check the exit
# rather than trusting the sleep, so a slow machine fails loudly instead of flakily.
_CHILD_DEATH_GRACE_S = 1.0

_SAMPLES_OVER_THE_BOUND = MCAP_QUEUE_MAX_ITEMS + 100


def _writer_that_cannot_open(tmp_path: Path) -> McapWriterProcess:
    """Start a writer whose output directory does not exist, so the child dies at open()."""
    writer = McapWriterProcess(tmp_path / "no_such_dir" / "ts.mcap")
    writer.start()
    time.sleep(_CHILD_DEATH_GRACE_S)
    assert writer.m_proc is not None
    assert writer.m_proc.exitcode is not None, "the child was expected to have died at open()"
    return writer


def test_writing_to_a_dead_writer_neither_blocks_nor_raises(tmp_path: Path) -> None:
    """`write` is called from the control loop, so it degrades instead of propagating."""
    writer = McapWriterProcess(tmp_path / "no_such_dir" / "ts.mcap")
    writer.start()
    time.sleep(_CHILD_DEATH_GRACE_S)

    for index in range(_SAMPLES_OVER_THE_BOUND):
        writer.write(TOPIC_JOINTS, index, {"q": [0.0] * 20})

    assert writer.dropped_samples == _SAMPLES_OVER_THE_BOUND
    with pytest.raises(McapWriterError):
        writer.close()


def test_close_returns_instead_of_hanging_when_the_writer_died(tmp_path: Path) -> None:
    """A backlog with no consumer must not wedge shutdown of the process commanding the arm.

    Unbounded, the parent's queue-feeder thread blocks forever at exit trying to flush into
    a pipe nobody drains, and `close()` never returns.
    """
    writer = _writer_that_cannot_open(tmp_path)
    for index in range(_SAMPLES_OVER_THE_BOUND):
        writer.write(TOPIC_JOINTS, index, {"q": [0.0] * 20})

    started = time.monotonic()
    with pytest.raises(McapWriterError, match="before the file was finished"):
        writer.close()
    assert time.monotonic() - started < _CHILD_DEATH_GRACE_S


def test_close_reports_the_exit_code_and_the_number_of_lost_samples(tmp_path: Path) -> None:
    """The message has to carry both, or "telemetry is missing" has no cause attached."""
    writer = _writer_that_cannot_open(tmp_path)
    writer.write(TOPIC_JOINTS, 1_000, {"q": [0.0]})

    with pytest.raises(McapWriterError) as raised:
        writer.close()

    message = str(raised.value)
    assert "exited with code" in message
    assert "1 sample(s) were dropped" in message


def test_the_queue_bound_holds_when_the_writer_is_alive_but_not_draining(
    tmp_path: Path,
) -> None:
    """A stalled writer costs counted samples, not unbounded memory in the caller."""
    writer = McapWriterProcess(tmp_path / "ts.mcap")
    # No start(): nothing consumes the queue, which is the stalled-writer shape without
    # depending on a child that happens to be slow.
    for index in range(_SAMPLES_OVER_THE_BOUND):
        writer.write(TOPIC_JOINTS, index, {"q": [0.0] * 20})

    assert writer.dropped_samples == _SAMPLES_OVER_THE_BOUND - MCAP_QUEUE_MAX_ITEMS
    writer.m_queue.cancel_join_thread()
