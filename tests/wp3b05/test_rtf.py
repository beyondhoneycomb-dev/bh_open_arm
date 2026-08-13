"""RTF, the four conditions, and the asymmetry that decides which coefficients get raised.

Nothing here measures a real codec. The clock is injected and the transcode is a callable, so
every assertion is about the arithmetic and the refusals — the codec's actual speed is the
resource-exclusive rig measurement this harness exists to carry, and a test that timed a real
encode would be asserting a property of whichever machine ran it.

The asymmetry in `coefficient_corrections` gets the most attention because it is the one an
implementation would plausibly get "tidy" and wrong: symmetric correction reads better and is
the failure. An over-estimated byte rate costs episodes; an under-estimated one ends a session
with a full disk and originals that cannot be cleared.
"""

from __future__ import annotations

import pytest

from backend.sensing.encoding.rtf import (
    RTF_CEILING,
    Condition,
    Encoder,
    RtfMeasurementError,
    StreamBytes,
    coefficient_corrections,
    condition_matrix,
    measure_rtf,
)

EPISODE_LENGTH_S = 20.0
STREAM = "left_wrist"
DEPTH_STREAM = "left_wrist_depth"


class _StepClock:
    """A clock that advances a fixed amount on its second read, so elapsed is exact."""

    def __init__(self, elapsed_s: float) -> None:
        self._elapsed_s = elapsed_s
        self._reads = 0

    def __call__(self) -> float:
        value = 0.0 if self._reads == 0 else self._elapsed_s
        self._reads += 1
        return value


def _one_stream(bytes_written: int) -> tuple[StreamBytes, ...]:
    return (
        StreamBytes(name=STREAM, bytes_written=bytes_written, episode_length_s=EPISODE_LENGTH_S),
    )


def test_the_matrix_is_four_cells_crossing_both_axes() -> None:
    """Two encoders by depth on/off. A list of three would not answer `PG-STO-001`."""
    matrix = condition_matrix()

    assert len(matrix) == 4
    assert {cell.encoder for cell in matrix} == set(Encoder)
    assert {cell.depth_included for cell in matrix} == {True, False}
    assert len({cell.label for cell in matrix}) == 4


def test_rtf_is_elapsed_over_episode_length() -> None:
    """The ratio, stated. Half the episode's duration is an RTF of 0.5."""
    measurement = measure_rtf(
        condition=Condition(Encoder.SOFTWARE_SVTAV1, depth_included=False),
        episode_length_s=EPISODE_LENGTH_S,
        transcode=lambda: _one_stream(1_000),
        clock=_StepClock(EPISODE_LENGTH_S / 2.0),
    )

    assert measurement.rtf == pytest.approx(0.5)
    assert measurement.keeps_up


def test_a_transcode_slower_than_the_episode_does_not_keep_up() -> None:
    """Above the ceiling the originals accumulate — the reason this is a gate."""
    measurement = measure_rtf(
        condition=Condition(Encoder.HARDWARE_NVENC, depth_included=True),
        episode_length_s=EPISODE_LENGTH_S,
        transcode=lambda: _one_stream(1_000),
        clock=_StepClock(EPISODE_LENGTH_S * 2.0),
    )

    assert measurement.rtf == pytest.approx(2.0)
    assert not measurement.keeps_up


def test_exactly_the_ceiling_still_counts_as_keeping_up() -> None:
    """The boundary is stated rather than left to a strict/non-strict slip."""
    measurement = measure_rtf(
        condition=Condition(Encoder.SOFTWARE_SVTAV1, depth_included=False),
        episode_length_s=EPISODE_LENGTH_S,
        transcode=lambda: _one_stream(1_000),
        clock=_StepClock(EPISODE_LENGTH_S * RTF_CEILING),
    )

    assert measurement.keeps_up


def test_a_zero_length_episode_is_refused_rather_than_reported_as_infinite() -> None:
    """Infinity would enter the gate as an encoder failure caused by the denominator."""
    with pytest.raises(RtfMeasurementError, match="above zero"):
        measure_rtf(
            condition=Condition(Encoder.SOFTWARE_SVTAV1, depth_included=False),
            episode_length_s=0.0,
            transcode=lambda: _one_stream(1_000),
        )


def test_the_transcode_runs_exactly_once() -> None:
    """A harness that ran it twice would report the second run's timing for the first's bytes."""
    calls = 0

    def transcode() -> tuple[StreamBytes, ...]:
        nonlocal calls
        calls += 1
        return _one_stream(1_000)

    measure_rtf(
        condition=Condition(Encoder.SOFTWARE_SVTAV1, depth_included=False),
        episode_length_s=EPISODE_LENGTH_S,
        transcode=transcode,
        clock=_StepClock(1.0),
    )

    assert calls == 1


def test_the_queue_high_water_mark_travels_with_the_measurement() -> None:
    """Acceptance ② wants the maximum depth beside the ratio, not in a separate report."""
    measurement = measure_rtf(
        condition=Condition(Encoder.SOFTWARE_SVTAV1, depth_included=True),
        episode_length_s=EPISODE_LENGTH_S,
        transcode=lambda: _one_stream(1_000),
        peak_queue_depth=37,
        clock=_StepClock(1.0),
    )

    assert measurement.peak_queue_depth == 37


def test_bytes_per_second_is_the_measured_size_over_the_episode() -> None:
    """The coefficient, stated. It is bytes over seconds and nothing derived from frame count."""
    stream = StreamBytes(name=STREAM, bytes_written=2_000, episode_length_s=EPISODE_LENGTH_S)

    assert stream.bytes_per_second == pytest.approx(100.0)


def test_an_under_estimated_coefficient_is_raised_to_what_was_measured() -> None:
    """The direction that ends a session with a full disk."""
    measured = (StreamBytes(name=STREAM, bytes_written=2_000, episode_length_s=EPISODE_LENGTH_S),)

    corrections = coefficient_corrections(measured, {STREAM: 50.0})

    assert corrections == {STREAM: pytest.approx(100.0)}


def test_an_over_estimated_coefficient_is_left_alone() -> None:
    """The asymmetry. Correcting this direction too would read tidier and be wrong.

    An over-estimate makes a disk budget pessimistic, which costs episodes and nothing else.
    Lowering it to the observed value would hand back exactly the headroom the pessimism bought.
    """
    measured = (StreamBytes(name=STREAM, bytes_written=2_000, episode_length_s=EPISODE_LENGTH_S),)

    assert coefficient_corrections(measured, {STREAM: 500.0}) == {}


def test_a_coefficient_that_exactly_matches_is_not_corrected() -> None:
    """Equality is covered, so the rule cannot drift into raising every stream every run."""
    measured = (StreamBytes(name=STREAM, bytes_written=2_000, episode_length_s=EPISODE_LENGTH_S),)

    assert coefficient_corrections(measured, {STREAM: 100.0}) == {}


def test_a_stream_the_table_never_declared_is_reported_not_skipped() -> None:
    """An unlisted stream is a coefficient of zero in every budget that reads the table.

    Skipping it is the same failure as declaring it too small, with no line to point at.
    """
    measured = (
        StreamBytes(name=DEPTH_STREAM, bytes_written=4_000, episode_length_s=EPISODE_LENGTH_S),
    )

    assert coefficient_corrections(measured, {}) == {DEPTH_STREAM: pytest.approx(200.0)}


def test_depth_is_corrected_on_its_own_coefficient() -> None:
    """Acceptance ④: depth is lossless 12-bit HEVC and does not scale like the colour streams.

    Averaging the two would be wrong in whichever direction the mix happened to fall, so a run
    that under-declared depth alone must raise depth alone.
    """
    measured = (
        StreamBytes(name=STREAM, bytes_written=2_000, episode_length_s=EPISODE_LENGTH_S),
        StreamBytes(name=DEPTH_STREAM, bytes_written=8_000, episode_length_s=EPISODE_LENGTH_S),
    )

    corrections = coefficient_corrections(measured, {STREAM: 500.0, DEPTH_STREAM: 100.0})

    assert corrections == {DEPTH_STREAM: pytest.approx(400.0)}
