"""FR-TRN-029: the trainer's output is streamed, persisted, and readable after end.

The dummy prints a known line per step; after the job finishes those lines must be
readable from the log store, which is the "잡 종료 후에도 조회 가능" the requirement
turns on.
"""

from __future__ import annotations

from pathlib import Path

from backend.training.orchestrator import JobState
from tests.wp4a01._support import make_orchestrator, make_spec


def test_logs_are_queryable_after_the_job_ends(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    job = make_spec("job", tmp_path / "run", steps=3, save_freq=1)

    orchestrator.submit(job)
    assert orchestrator.wait("job", timeout=15.0) is JobState.DONE

    # Read AFTER the job has finished — the file persists, not just a live stream.
    lines = orchestrator.mLogStore.read("job")
    assert any("step=1" in line for line in lines)
    assert any("step=3" in line for line in lines)
    assert any("done step=3" in line for line in lines)
    assert orchestrator.mLogStore.exists("job")


def test_live_subscriber_receives_lines(tmp_path: Path) -> None:
    # The log writer fans each line to subscribers as it is teed — the live-stream
    # half of FR-TRN-029. Exercised at the store level to avoid racing a subprocess.
    from backend.training.orchestrator import LogStore

    received: list[str] = []
    store = LogStore(tmp_path / "logs")
    writer = store.open_writer("j")
    writer.subscribe(received.append)
    writer.append("hello")
    writer.append("world\n")
    writer.close()

    assert received == ["hello", "world"]
    assert store.read("j") == ["hello", "world"]
