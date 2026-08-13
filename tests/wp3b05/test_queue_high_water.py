"""The encoder queue's maximum depth, which `PG-STO-001` acceptance ② asks for by name.

The worker already counted threshold crossings, and that number does not answer the question: a
queue that crossed four times might have reached five or five hundred, and it is the depth that
back-computes the disk-exhaustion time a `DEGRADED_ACCEPTED` verdict rests on. Reading
`outstanding` after a run answers even less — by then the queue has drained, so it reports zero
on exactly the runs that mattered.

Every test here gates the transcode so the queue depth is decided by the test rather than by how
fast the machine drains it. Nothing asserts a duration.
"""

from __future__ import annotations

import threading
import time
import warnings

import pytest

from backend.sensing.encoding import BackpressureWarning, TranscodeWorker
from tests.wp3b05.support import ControllableTranscoder, empty_job

# Small enough that a handful of submits crosses it, so the backpressure path is exercised by
# the same runs that measure the depth.
MAXSIZE = 2

# How many episodes the deep run submits. Above `MAXSIZE` so the mark has somewhere to climb to.
SUBMITTED = 5

# The bound every gate release uses. Generous, because a slow machine must make these tests slow
# rather than red.
JOIN_BOUND_S = 5.0


def _worker(gate: threading.Event) -> tuple[TranscodeWorker, ControllableTranscoder]:
    """A worker whose transcode blocks on `gate`, so the queue depth is the test's to choose."""
    transcoder = ControllableTranscoder(gate=gate)
    return TranscodeWorker(transcode_fn=transcoder, encoder_queue_maxsize=MAXSIZE), transcoder


def test_a_fresh_worker_has_no_peak(tmp_path) -> None:
    """Zero before anything is submitted, so a run that submitted nothing cannot report depth."""
    gate = threading.Event()
    worker, _ = _worker(gate)
    try:
        assert worker.peak_outstanding == 0
    finally:
        gate.set()
        worker.close()


def test_the_peak_records_the_deepest_the_queue_ever_got(tmp_path) -> None:
    """The mark climbs with the queue while the transcode is held."""
    gate = threading.Event()
    worker, _ = _worker(gate)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", BackpressureWarning)
            for index in range(SUBMITTED):
                worker.submit(empty_job(tmp_path, index))

        assert worker.peak_outstanding == SUBMITTED
    finally:
        gate.set()
        worker.close()


def test_the_peak_survives_the_queue_draining(tmp_path) -> None:
    """The property `outstanding` cannot have: after the drain it still reports the maximum.

    This is the whole reason the field exists. A report written after a session would read
    `outstanding` as zero and record that the encoder never fell behind.
    """
    gate = threading.Event()
    worker, _ = _worker(gate)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", BackpressureWarning)
        for index in range(SUBMITTED):
            worker.submit(empty_job(tmp_path, index))
    gate.set()
    worker.close()

    assert worker.outstanding == 0
    assert worker.peak_outstanding == SUBMITTED


def test_the_peak_is_a_maximum_not_the_latest_depth(tmp_path) -> None:
    """A second, shallower burst must not lower the mark."""
    gate = threading.Event()
    worker, _ = _worker(gate)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", BackpressureWarning)
        for index in range(SUBMITTED):
            worker.submit(empty_job(tmp_path, index))
    gate.set()
    worker.close()
    deep = worker.peak_outstanding

    shallow_gate = threading.Event()
    shallow, _ = _worker(shallow_gate)
    shallow.submit(empty_job(tmp_path, 0))
    shallow_gate.set()
    shallow.close()

    assert deep == SUBMITTED
    assert shallow.peak_outstanding < deep


def test_the_peak_and_the_crossing_count_are_different_numbers(tmp_path) -> None:
    """Crossings say how often, depth says how deep, and the gate asks for the second.

    Pinned as an inequality so an implementation cannot satisfy acceptance ② by aliasing the
    field it already had.
    """
    gate = threading.Event()
    worker, _ = _worker(gate)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", BackpressureWarning)
            for index in range(SUBMITTED):
                worker.submit(empty_job(tmp_path, index))

        assert worker.peak_outstanding == SUBMITTED
        assert worker.backpressure_events == SUBMITTED - MAXSIZE
        assert worker.peak_outstanding != worker.backpressure_events
    finally:
        gate.set()
        worker.close()


def test_a_run_that_never_crosses_the_threshold_still_reports_its_depth(tmp_path) -> None:
    """Depth is measured whether or not the warning fired; the two are independent facts."""
    gate = threading.Event()
    worker, _ = _worker(gate)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", BackpressureWarning)
            worker.submit(empty_job(tmp_path, 0))

        assert worker.backpressure_events == 0
        assert worker.peak_outstanding == 1
    finally:
        gate.set()
        worker.close()


@pytest.mark.parametrize("submitted", [1, MAXSIZE, SUBMITTED])
def test_the_peak_equals_the_number_submitted_while_the_transcode_is_held(
    tmp_path, submitted: int
) -> None:
    """With the worker blocked, nothing completes, so the depth is exactly the submit count."""
    gate = threading.Event()
    worker, _ = _worker(gate)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", BackpressureWarning)
            for index in range(submitted):
                worker.submit(empty_job(tmp_path, index))

        assert worker.peak_outstanding == submitted
    finally:
        gate.set()
        worker.close()


def test_the_peak_holds_after_the_queue_drains_and_refills_shallower(tmp_path) -> None:
    """The case a monotonic queue never produces, and the only one `max` is needed for.

    Every other test here holds the transcode from the first submit, so the depth only ever
    climbs — and against a monotonic series, taking the maximum and taking the latest value are
    the same answer. A deep burst that drains and is followed by a shallower one is what
    separates them, and it is the ordinary shape of a session: a long recording backs the
    encoder up, the operator pauses, and the next recording is short.
    """
    deep_gate = threading.Event()
    transcoder = ControllableTranscoder(gate=deep_gate)
    worker = TranscodeWorker(transcode_fn=transcoder, encoder_queue_maxsize=MAXSIZE)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", BackpressureWarning)
            for index in range(SUBMITTED):
                worker.submit(empty_job(tmp_path, index))
        assert worker.peak_outstanding == SUBMITTED

        # Let the deep burst drain completely, then send one more.
        deep_gate.set()
        deadline = time.perf_counter() + JOIN_BOUND_S
        while worker.outstanding > 0 and time.perf_counter() < deadline:
            time.sleep(0.001)
        assert worker.outstanding == 0, "the deep burst never drained"

        worker.submit(empty_job(tmp_path, SUBMITTED))

        assert worker.peak_outstanding == SUBMITTED
    finally:
        deep_gate.set()
        worker.close()
