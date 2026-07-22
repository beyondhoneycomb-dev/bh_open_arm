"""WP-3B-05 ③ — crossing encoder_queue_maxsize raises a backpressure warning.

Backpressure is a warning, not a block (`07` NFR-REC-005): the originals are safe on
disk, so when the transcode falls behind the outstanding count grows and the worker
warns once it passes `encoder_queue_maxsize`. It must warn, and it must not block —
these check both, driving the worker with a gated transcode so the outstanding count
is deterministic.
"""

from __future__ import annotations

import threading
import time
import warnings

import pytest

from backend.sensing.encoding import BackpressureEvent, BackpressureWarning, TranscodeWorker
from tests.wp3b05.support import ControllableTranscoder, empty_job

# Five submits against a gated transcode return well under the gate's timeout when
# submit is non-blocking; a blocking submit would take the transcode's full wait.
_NON_BLOCKING_BOUND_S = 1.0


def test_warning_raised_when_outstanding_exceeds_threshold(tmp_path):
    """The submit that pushes outstanding past the threshold warns; earlier ones do not."""
    gate = threading.Event()
    events: list[BackpressureEvent] = []
    worker = TranscodeWorker(
        ControllableTranscoder(gate=gate),
        encoder_queue_maxsize=2,
        on_backpressure=events.append,
    )
    try:
        # Outstanding 1 then 2: at or under the threshold, no warning.
        worker.submit(empty_job(tmp_path, 0))
        worker.submit(empty_job(tmp_path, 1))
        assert worker.backpressure_events == 0

        # Outstanding 3: over the threshold, warns on this submit.
        with pytest.warns(BackpressureWarning):
            worker.submit(empty_job(tmp_path, 2))

        assert worker.backpressure_events == 1
        assert len(events) == 1
        assert events[0].outstanding == 3
        assert events[0].threshold == 2
    finally:
        gate.set()
        worker.wait_idle(timeout=5.0)
        worker.close(timeout=5.0)


def test_submit_does_not_block_under_backpressure(tmp_path):
    """Even over the threshold, submit returns rather than blocking on the transcode."""
    gate = threading.Event()
    worker = TranscodeWorker(ControllableTranscoder(gate=gate), encoder_queue_maxsize=1)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", BackpressureWarning)
            started = time.monotonic()
            for episode_index in range(5):
                worker.submit(empty_job(tmp_path, episode_index))
            elapsed = time.monotonic() - started

        assert elapsed < _NON_BLOCKING_BOUND_S
        assert worker.outstanding == 5
    finally:
        gate.set()
        worker.wait_idle(timeout=5.0)
        worker.close(timeout=5.0)
