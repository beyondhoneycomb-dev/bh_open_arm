"""Acceptance ① and ② — crash report carries all four fields under SIGKILL and OOM.

Both deaths are uncatchable, so the report is assembled by a supervisor *after* death from the
context the subject spooled while alive. The two paths converge: the OOM killer's mechanism is
SIGKILL, so an OOM simulation produces the same four fields as an external SIGKILL. Each test
asserts the presence of `{exit code, signal, 30 s ring buffer, last state transition}` in full.
"""

from __future__ import annotations

import signal
from pathlib import Path

from ops.telemetry.constants import SIGNAL_EXIT_OFFSET
from ops.telemetry.crash_report import REQUIRED_FIELDS
from ops.telemetry.crash_reporter import SupervisedLoop, decode_exit


def test_sigkill_injection_yields_all_four_fields(tmp_path: Path) -> None:
    """An external SIGKILL produces a report with all four required fields present."""
    with SupervisedLoop(tmp_path) as loop:
        loop.inject_sigkill()
        report = loop.collect()

    assert report.has_all_required_fields()
    assert report.signal == signal.SIGKILL
    assert report.exit_code == SIGNAL_EXIT_OFFSET + signal.SIGKILL
    assert len(report.ring_buffer) > 0
    assert report.last_transition is not None
    assert set(report.field_presence()) == set(REQUIRED_FIELDS)
    assert all(report.field_presence().values())


def test_oom_simulation_yields_the_same_four_fields(tmp_path: Path) -> None:
    """An OOM simulation (grow RSS, self-SIGKILL) yields the identical four fields."""
    with SupervisedLoop(tmp_path) as loop:
        loop.request_oom()
        report = loop.collect()

    assert report.has_all_required_fields()
    assert report.signal == signal.SIGKILL
    assert report.exit_code == SIGNAL_EXIT_OFFSET + signal.SIGKILL
    assert len(report.ring_buffer) > 0
    assert report.last_transition is not None


def test_last_state_transition_is_the_most_recent_one(tmp_path: Path) -> None:
    """The report's last transition is the final state change the subject recorded."""
    with SupervisedLoop(tmp_path) as loop:
        loop.inject_sigkill()
        report = loop.collect()

    assert report.last_transition is not None
    assert report.last_transition.to_state == "TELEOP"


def test_decode_exit_splits_signal_from_code() -> None:
    """A signal death decodes to `(128 + signal, signal)`; a plain exit keeps no signal."""
    assert decode_exit(-signal.SIGKILL) == (SIGNAL_EXIT_OFFSET + signal.SIGKILL, signal.SIGKILL)
    assert decode_exit(0) == (0, None)
    assert decode_exit(3) == (3, None)
