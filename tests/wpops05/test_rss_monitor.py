"""Acceptance ⑥ — the RSS-slope monitor detects an artificial leak.

Two halves. The slope math is pinned with synthetic samples so the detection rule is exact and
deterministic. Then the real fixture (`_leak_fixture`) is driven: in `leak` mode its resident
set climbs on every step and the monitor, sampling the real `/proc/<pid>/status`, must flag it;
in `steady` mode its RSS is flat and the monitor must not.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ops.telemetry.constants import RSS_LEAK_SLOPE_BYTES_PER_S
from ops.telemetry.rss_monitor import RssSlopeMonitor

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEAK_MODULE = "ops.telemetry._leak_fixture"
_READY_PREFIX = "READY "
_STEPS = 8


def test_synthetic_steady_rss_is_not_a_leak() -> None:
    """Flat RSS gives a ~zero slope and is not flagged."""
    monitor = RssSlopeMonitor()
    for t in range(10):
        monitor.add(float(t), 50_000_000)
    slope = monitor.slope_bytes_per_s()
    assert slope is not None
    assert abs(slope) < 1.0
    assert not monitor.leaking()


def test_synthetic_growing_rss_is_a_leak() -> None:
    """RSS climbing well above the threshold per unit time is flagged."""
    monitor = RssSlopeMonitor()
    per_step = int(RSS_LEAK_SLOPE_BYTES_PER_S * 10)
    for t in range(10):
        monitor.add(float(t), 50_000_000 + t * per_step)
    slope = monitor.slope_bytes_per_s()
    assert slope is not None
    assert slope > RSS_LEAK_SLOPE_BYTES_PER_S
    assert monitor.leaking()


def test_slope_undefined_below_minimum_samples() -> None:
    """Fewer than the minimum samples yields no slope, hence no leak verdict."""
    monitor = RssSlopeMonitor(min_samples=4)
    monitor.add(0.0, 1_000)
    monitor.add(1.0, 2_000)
    assert monitor.slope_bytes_per_s() is None
    assert not monitor.leaking()


@contextmanager
def _leak_fixture(mode: str) -> Iterator[tuple[subprocess.Popen[str], int]]:
    """Spawn the leak fixture in a mode, yield `(proc, pid)`, and tear it down."""
    proc = subprocess.Popen(
        [sys.executable, "-m", _LEAK_MODULE, mode],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert proc.stdout is not None
    ready = proc.stdout.readline()
    assert ready.startswith(_READY_PREFIX)
    pid = int(ready[len(_READY_PREFIX) :].strip())
    try:
        yield proc, pid
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()


def _drive(proc: subprocess.Popen[str], monitor: RssSlopeMonitor, pid: int) -> None:
    """Step the fixture `_STEPS` times, sampling real RSS after each acknowledged step.

    The step index is the time axis: the monitor only needs a monotonic independent variable,
    and using the index keeps the slope free of wall-clock scheduling jitter.
    """
    assert proc.stdin is not None
    assert proc.stdout is not None
    for step in range(_STEPS):
        proc.stdin.write("\n")
        proc.stdin.flush()
        assert proc.stdout.readline().strip() == "STEP"
        monitor.add_reading(float(step), pid)


def test_real_leak_fixture_is_detected() -> None:
    """A subprocess whose RSS genuinely climbs is flagged as leaking from real /proc reads."""
    monitor = RssSlopeMonitor()
    with _leak_fixture("leak") as (proc, pid):
        _drive(proc, monitor, pid)
    assert monitor.leaking()


def test_real_steady_fixture_is_not_flagged() -> None:
    """A subprocess with flat RSS is not flagged — the monitor does not over-fire."""
    monitor = RssSlopeMonitor()
    with _leak_fixture("steady") as (proc, pid):
        _drive(proc, monitor, pid)
    assert not monitor.leaking()
