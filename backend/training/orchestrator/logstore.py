"""Per-job log capture: tee the trainer's output to disk, queryable after it ends.

FR-TRN-029 wants three things at once: the trainer's stdout/stderr streamed live,
persisted to a file, and still readable after the job finishes. This module is all
three. A `LogWriter` is opened for a running job; the launcher's reader thread
feeds it lines as they arrive, and every line is both appended to the job's file
and fanned out to any live subscriber. Once the job ends the writer is closed, and
the file remains — `read` serves it whether or not the job is still alive, which is
the "잡 종료 후에도 조회 가능" the requirement turns on.

Ownership/threading: one `LogWriter` is written by exactly one reader thread. The
`LogStore` that hands them out is otherwise stateless — the file is the state — so
a `read` from any thread at any time is just a file read.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from backend.training.orchestrator.constants import LOG_FILE_SUFFIX

# A live subscriber receives each line as it is teed. The MCAP/GUI stream is the
# real consumer; tests attach a list's append.
LogSubscriber = Callable[[str], None]


class LogWriter:
    """An open sink for one job's log lines: appends to file, fans out live.

    Ownership: the launcher's single reader thread owns the write side and calls
    `append`/`close`. Subscribers are notified on that same thread, so a slow
    subscriber slows the reader — subscribers are expected to be cheap (enqueue and
    return), never to block on I/O of their own.
    """

    def __init__(self, path: Path) -> None:
        """Open (truncating) the log file for a job.

        Args:
            path: The job's log file path.
        """
        self.mPath = path
        self.mPath.parent.mkdir(parents=True, exist_ok=True)
        self.mHandle = self.mPath.open("w", encoding="utf-8")
        self.mSubscribers: list[LogSubscriber] = []
        self.mClosed = False

    def subscribe(self, subscriber: LogSubscriber) -> None:
        """Register a live subscriber to receive each subsequent line.

        Args:
            subscriber: Callable invoked with each appended line.
        """
        self.mSubscribers.append(subscriber)

    def append(self, line: str) -> None:
        """Append one line to the file and fan it out to subscribers.

        The line is flushed immediately so a concurrent `read` sees it and a crash
        does not swallow the final lines that a classifier (FR-OPS-024) needs.

        Args:
            line: One log line, newline-terminated or not.
        """
        if self.mClosed:
            return
        text = line if line.endswith("\n") else line + "\n"
        self.mHandle.write(text)
        self.mHandle.flush()
        for subscriber in self.mSubscribers:
            subscriber(line.rstrip("\n"))

    def close(self) -> None:
        """Close the file. Idempotent; the persisted lines remain readable."""
        if self.mClosed:
            return
        self.mClosed = True
        self.mHandle.close()


class LogStore:
    """Hands out per-job log writers and reads persisted logs back.

    Attributes are derived from one base directory; there is no in-memory index,
    so a log written in an earlier process is still readable here.
    """

    def __init__(self, base_dir: Path) -> None:
        """Create a store rooted at a directory of per-job log files.

        Args:
            base_dir: Directory the `<job_id>.log` files live in.
        """
        self.mBaseDir = base_dir

    def path_for(self, job_id: str) -> Path:
        """Return the log file path for a job.

        Args:
            job_id: The job.

        Returns:
            (Path) `<base_dir>/<job_id>.log`.
        """
        return self.mBaseDir / f"{job_id}{LOG_FILE_SUFFIX}"

    def open_writer(self, job_id: str) -> LogWriter:
        """Open a fresh writer for a job about to run.

        Args:
            job_id: The job.

        Returns:
            (LogWriter) An open writer over the job's log file.
        """
        return LogWriter(self.path_for(job_id))

    def read(self, job_id: str) -> list[str]:
        """Read a job's persisted log lines, whether or not the job still runs.

        Args:
            job_id: The job.

        Returns:
            (list[str]) The lines, without trailing newlines; empty when no log
                file exists for the job.
        """
        path = self.path_for(job_id)
        if not path.is_file():
            return []
        return path.read_text(encoding="utf-8").splitlines()

    def exists(self, job_id: str) -> bool:
        """Report whether a persisted log exists for a job.

        Args:
            job_id: The job.

        Returns:
            (bool) True when the log file is present.
        """
        return self.path_for(job_id).is_file()
