"""The synthetic load stages produce their declared shapes, and no-load holds no GIL.

The load generator is the deliverable's core: five-stream grab, lossless-PNG write to
a byte budget, dataset write, WS serialization. This suite pins each stage's declared
output and the property that a no-load profile spins the GIL zero times — the hinge
of the acceptance ③ anti-rig behaviour — plus that the runner starts and always stops
its worker.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from sim.harness.gil_load import (
    LoadLocation,
    LoadRunner,
    _gil_spin_iterations,
    encode_lossless_png,
    serialize_ws,
    simulate_grab,
)
from sim.harness.load_profile import LoadProfile

_REAL = LoadProfile(5, 320, 240, 32 * 1024, 128 * 1024)


def test_grab_returns_one_buffer_per_stream() -> None:
    """Five streams give five HxWx3 frames of the profile's resolution."""
    frames = simulate_grab(_REAL)
    assert len(frames) == 5
    assert frames[0].shape == (240, 320, 3)


def test_png_stage_hits_the_byte_budget() -> None:
    """The lossless-PNG stage emits exactly the declared bytes per frame."""
    frame = simulate_grab(_REAL)[0]
    assert len(encode_lossless_png(frame, 32 * 1024)) == 32 * 1024
    assert len(encode_lossless_png(frame, 4)) == 4


def test_serialize_stage_hits_the_byte_budget() -> None:
    """The WS-serialization stage emits exactly the declared bytes per tick."""
    assert len(serialize_ws(_REAL, tick=3)) == 128 * 1024
    assert serialize_ws(LoadProfile(5, 320, 240, 1024, 0), tick=0) == b""


def test_spin_is_zero_for_no_load_and_positive_for_real() -> None:
    """A no-load profile holds the GIL zero iterations; a real one holds it many."""
    assert _gil_spin_iterations(LoadProfile(0, 320, 240, 0, 0)) == 0
    assert _gil_spin_iterations(LoadProfile(5, 320, 240, 0, 0)) == 0
    assert _gil_spin_iterations(_REAL) > 0


def test_same_process_runner_starts_and_stops(tmp_path: Path) -> None:
    """The same-process runner starts a worker and joins it on exit."""
    with LoadRunner(_REAL, LoadLocation.SAME_PROCESS, str(tmp_path)) as runner:
        time.sleep(0.05)
        assert runner._thread is not None
        assert runner._thread.is_alive()
    assert not runner._thread.is_alive()


def test_separate_process_runner_starts_and_stops(tmp_path: Path) -> None:
    """The separate-process runner starts a process and joins it on exit."""
    with LoadRunner(_REAL, LoadLocation.SEPARATE_PROCESS, str(tmp_path)) as runner:
        time.sleep(0.1)
        assert runner._process is not None
        assert runner._process.is_alive()
    assert not runner._process.is_alive()


def test_none_runner_starts_no_worker(tmp_path: Path) -> None:
    """The idle baseline runner owns and starts nothing."""
    with LoadRunner(_REAL, LoadLocation.NONE, str(tmp_path)) as runner:
        assert runner._thread is None
        assert runner._process is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
