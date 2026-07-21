"""System timeseries to MCAP, written from a *separate process* (`14` FR-OPS-006, `15` NFR-PRF-038).

FR-OPS-006 fixes the storage format: system timeseries — joints, commands, diagnostics, CAN
traces, video metadata — are MCAP, written with the `mcap` Python library directly. rosbag2
is explicitly banned; `ros_staticcheck` proves the ban holds across this package.

NFR-PRF-038 requires the writer to run off the control loop's process, so serialization and
disk I/O cannot steal from the real-time path. `McapWriterProcess` is that boundary: the
control loop calls `write`, which only enqueues; a child process owns the file and does every
costly step. `writer_pid` is therefore never the caller's PID, which the acceptance gate ④
asserts directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any

from mcap.reader import make_reader
from mcap.writer import Writer

# One queue item is `(topic, log_time_ns, payload_bytes)`; None is the shutdown sentinel.
_QueueItem = tuple[str, int, bytes] | None

# A permissive JSON schema: the channel contract is the topic, not a rigid per-message shape
# (D-12 keeps the camera/telemetry registry name-based, not a frozen schema).
_GENERIC_JSON_SCHEMA = json.dumps({"type": "object"}).encode("utf-8")


def _writer_worker(path: str, queue: Queue[_QueueItem]) -> None:
    """Own the MCAP file in a child process, draining the queue until the sentinel.

    Schemas and channels are registered lazily on first sight of a topic, so a caller need
    not declare topics up front. The writer is finished exactly once, on the sentinel, so the
    file's summary section is always well-formed for the reader.

    Args:
        path: Output `.mcap` path.
        queue: Inbound queue of `(topic, log_time_ns, payload)` items and one None sentinel.
    """
    with open(path, "wb") as handle:  # noqa: PTH123  (mcap.Writer takes a binary file object)
        writer = Writer(handle)
        writer.start()
        schema_id = writer.register_schema(
            name="oa.TimeseriesSample",
            encoding="jsonschema",
            data=_GENERIC_JSON_SCHEMA,
        )
        channels: dict[str, int] = {}
        while True:
            item = queue.get()
            if item is None:
                break
            topic, log_time_ns, payload = item
            if topic not in channels:
                channels[topic] = writer.register_channel(
                    topic=topic,
                    message_encoding="json",
                    schema_id=schema_id,
                )
            writer.add_message(
                channel_id=channels[topic],
                log_time=log_time_ns,
                data=payload,
                publish_time=log_time_ns,
            )
        writer.finish()


class McapWriterProcess:
    """A handle to the separate process that writes the MCAP timeseries.

    Ownership/lifecycle: `start` spawns the child; `write` enqueues from the control-loop
    process and returns immediately; `close` sends the sentinel and joins. The child, not the
    caller, owns the file descriptor and the `Writer`.

    Args:
        path: Output `.mcap` path.
    """

    def __init__(self, path: Path) -> None:
        self.m_path = path
        self.m_queue: Queue[_QueueItem] = Queue()
        self.m_proc: Process | None = None

    def start(self) -> None:
        """Spawn the writer child process."""
        proc = Process(target=_writer_worker, args=(str(self.m_path), self.m_queue))
        proc.start()
        self.m_proc = proc

    @property
    def writer_pid(self) -> int:
        """Return the writer child's PID.

        Returns:
            (int) The child PID; distinct from the control loop's own PID by construction.

        Raises:
            RuntimeError: If the writer has not been started.
        """
        if self.m_proc is None or self.m_proc.pid is None:
            raise RuntimeError("writer process not started")
        return self.m_proc.pid

    def write(self, topic: str, log_time_ns: int, payload: dict[str, Any]) -> None:
        """Enqueue one timeseries sample for the writer process.

        Args:
            topic: One of the FR-OPS-006 channels.
            log_time_ns: Sample time in nanoseconds.
            payload: JSON-serializable sample body.
        """
        self.m_queue.put((topic, log_time_ns, json.dumps(payload).encode("utf-8")))

    def close(self) -> None:
        """Send the shutdown sentinel and join the writer process."""
        if self.m_proc is None:
            return
        self.m_queue.put(None)
        self.m_proc.join()
        self.m_queue.close()
        self.m_queue.join_thread()


@dataclass
class McapMessage:
    """One message read back from an MCAP file.

    Attributes:
        topic: The channel topic.
        log_time_ns: The stored log time in nanoseconds.
        payload: The decoded JSON body.
    """

    topic: str
    log_time_ns: int
    payload: dict[str, Any]


def load_mcap(path: Path) -> list[McapMessage]:
    """Load an MCAP file with the standard reader and decode its JSON messages.

    This is the acceptance ⑤ round-trip: a file the separate writer produced must load under
    the ordinary `mcap` reader with no rosbag2 involvement.

    Args:
        path: The `.mcap` file to read.

    Returns:
        (list[McapMessage]) Messages in file order.
    """
    messages: list[McapMessage] = []
    with open(path, "rb") as handle:  # noqa: PTH123  (make_reader takes a binary file object)
        reader = make_reader(handle)
        for _schema, channel, message in reader.iter_messages():
            messages.append(
                McapMessage(
                    topic=channel.topic,
                    log_time_ns=message.log_time,
                    payload=json.loads(message.data),
                )
            )
    return messages
