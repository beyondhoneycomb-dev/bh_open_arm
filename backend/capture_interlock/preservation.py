"""The four capture-preservation checks (`02b` §7.2 WP-3C-06).

Each check compares the raw capture source against the converted dataset on one
facet the conversion must have preserved, all anchored to the raw source's original
frame count N and its capture instants:

  ① frame count      — every converted stream (mp4 and depth) encodes exactly N frames.
  ② video length     — every converted video's declared temporal span covers exactly N frames.
  ③ row count        — the converted data parquet holds exactly `fps × episode length` rows.
  ④ capture_ts       — the converted capture_ts is strictly monotonic per slot and content-hash
                       identical to the raw source's (the before/after preservation compare).

These are orthogonal to WP-3D-05, which never sees the raw source: WP-3D-05 checks
the converted dataset's *internal* consistency, this band checks the conversion
*preserved the original*. No check may crash the run — an unreadable facet becomes a
FAIL for that check, because a facet that cannot be established must never pass a
preservation check and thereby license an irreversible delete.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from backend.capture_interlock.constants import (
    CAPTURE_TS_HASH_ALGORITHM,
    CHECK_CAPTURE_TS,
    CHECK_FRAME_COUNT,
    CHECK_ROW_COUNT,
    CHECK_VIDEO_LENGTH,
)
from backend.capture_interlock.converted import ConvertedDataset, ConvertedReadError
from backend.capture_interlock.report import (
    EpisodePreservation,
    PreservationCheck,
    failed,
    passed,
)
from backend.capture_interlock.source import CaptureSourceEpisode
from contracts.capture.schema import CaptureSidecar
from contracts.prim import CameraSlotKey


def capture_ts_content_hash(sidecar: CaptureSidecar) -> str:
    """Content-hash a capture-timestamp sidecar's per-slot capture instants.

    The digest is SHA-256 over each slot's `capture_ts` sequence in frame order,
    slots taken in a stable sorted order. It is order- and length-sensitive by
    construction: a reordered pair of instants changes a sequence, and a dropped
    frame shortens one, so either changes the digest — which is what makes the
    before/after compare (④) able to detect a conversion that did not preserve
    capture time.

    Args:
        sidecar: The capture-timestamp sidecar to hash.

    Returns:
        (str) The hex digest of the canonical per-slot instant serialization.
    """
    digest = hashlib.new(CAPTURE_TS_HASH_ALGORITHM)
    for slot in sidecar.slots():
        digest.update(slot.value.encode("utf-8"))
        for row in sidecar.rows:
            digest.update(str(row.slots[slot].capture_ts.mono_ns).encode("utf-8"))
            digest.update(b",")
    return digest.hexdigest()


def _slot_is_monotonic(sidecar: CaptureSidecar, slot: CameraSlotKey) -> bool:
    """Whether a slot's capture instants strictly increase across the episode."""
    values = [row.slots[slot].capture_ts.mono_ns for row in sidecar.rows]
    return all(later > earlier for earlier, later in zip(values, values[1:], strict=False))


def check_frame_count(
    source: CaptureSourceEpisode, converted: ConvertedDataset
) -> PreservationCheck:
    """① Every converted stream's encoded frame count equals the original count N."""
    try:
        counts = converted.stream_frame_counts(source.episode_index)
    except ConvertedReadError as bad:
        return failed(CHECK_FRAME_COUNT, f"cannot read converted stream frame counts: {bad}")
    for stream in counts:
        if stream.frame_count != source.length:
            kind = "depth" if stream.is_depth else "video"
            return failed(
                CHECK_FRAME_COUNT,
                f"{kind} {stream.image_key!r} encodes {stream.frame_count} frame(s), "
                f"original captured {source.length}",
            )
    if not counts:
        return failed(CHECK_FRAME_COUNT, "converted dataset declares no streams to count")
    return passed(
        CHECK_FRAME_COUNT,
        f"{len(counts)} stream(s) each encode the original {source.length} frames",
    )


def check_video_length(
    source: CaptureSourceEpisode, converted: ConvertedDataset
) -> PreservationCheck:
    """② Every converted video's declared temporal span covers the original N frames."""
    try:
        spans = converted.video_declared_spans(source.episode_index)
    except ConvertedReadError as bad:
        return failed(CHECK_VIDEO_LENGTH, f"cannot read converted video spans: {bad}")
    for span in spans:
        if span.declared_frames != source.length:
            return failed(
                CHECK_VIDEO_LENGTH,
                f"video {span.image_key!r} declares a span of {span.declared_frames} frame(s) "
                f"({span.declared_frames / source.fps:.4f}s), episode length is {source.length} "
                f"frame(s) ({source.duration_seconds:.4f}s)",
            )
    if not spans:
        return passed(CHECK_VIDEO_LENGTH, "no RGB video streams carry a declared length")
    return passed(
        CHECK_VIDEO_LENGTH,
        f"{len(spans)} video(s) each declare the episode length of {source.length} frames",
    )


def check_row_count(source: CaptureSourceEpisode, converted: ConvertedDataset) -> PreservationCheck:
    """③ The converted data-parquet row count equals `fps × episode length`."""
    expected = round(converted.fps * source.duration_seconds)
    try:
        actual = converted.parquet_row_count(source.episode_index)
    except ConvertedReadError as bad:
        return failed(CHECK_ROW_COUNT, f"cannot count converted data-parquet rows: {bad}")
    if actual != expected:
        return failed(
            CHECK_ROW_COUNT,
            f"data parquet holds {actual} row(s) for the episode, expected "
            f"fps({converted.fps}) × length({source.duration_seconds:.4f}s) = {expected}",
        )
    return passed(CHECK_ROW_COUNT, f"{actual} rows match fps × episode length")


def check_capture_ts(
    source: CaptureSourceEpisode, converted: ConvertedDataset
) -> PreservationCheck:
    """④ Converted capture_ts is monotonic per slot and preserved (before/after hash)."""
    try:
        converted_sidecar = converted.capture_sidecar(source.episode_index)
    except ConvertedReadError as bad:
        return failed(CHECK_CAPTURE_TS, f"cannot read converted capture_ts sidecar: {bad}")

    for slot in converted_sidecar.slots():
        if not _slot_is_monotonic(converted_sidecar, slot):
            return failed(
                CHECK_CAPTURE_TS,
                f"converted capture_ts for slot {slot.value!r} is not strictly increasing "
                "(a reordered or duplicated capture instant)",
            )

    raw_hash = capture_ts_content_hash(source.sidecar)
    converted_hash = capture_ts_content_hash(converted_sidecar)
    if raw_hash != converted_hash:
        return failed(
            CHECK_CAPTURE_TS,
            f"converted capture_ts content hash {converted_hash[:12]}… does not match the raw "
            f"source hash {raw_hash[:12]}… (capture time was not preserved by the conversion)",
        )
    return passed(
        CHECK_CAPTURE_TS, "capture_ts is monotonic per slot and content-identical to the raw source"
    )


CaptureCheck = Callable[[CaptureSourceEpisode, ConvertedDataset], PreservationCheck]

# Each check paired with the id it reports under, so a check that crashes still
# produces a result under its own id (which then counts as a required-check failure
# for the episode) rather than an unrecognised id the required-set test would read
# as a missing check.
_CAPTURE_CHECKS: tuple[tuple[str, CaptureCheck], ...] = (
    (CHECK_FRAME_COUNT, check_frame_count),
    (CHECK_VIDEO_LENGTH, check_video_length),
    (CHECK_ROW_COUNT, check_row_count),
    (CHECK_CAPTURE_TS, check_capture_ts),
)


def check_episode(source: CaptureSourceEpisode, converted: ConvertedDataset) -> EpisodePreservation:
    """Run all four capture-preservation checks for one episode.

    Every check runs even when an earlier one failed, so the report names every way
    the conversion diverged from the original rather than just the first.

    Args:
        source: The raw source episode (the original ground truth).
        converted: The converted dataset reader.

    Returns:
        (EpisodePreservation) The four results and the episode's PRESERVED/MISMATCH
            verdict.
    """
    results = tuple(_run_check(name, check, source, converted) for name, check in _CAPTURE_CHECKS)
    return EpisodePreservation(episode_index=source.episode_index, results=results)


def _run_check(
    name: str,
    check: CaptureCheck,
    source: CaptureSourceEpisode,
    converted: ConvertedDataset,
) -> PreservationCheck:
    """Run one check, turning any unexpected exception into a FAIL under its own id.

    A check that dies on a corrupt facet must leave the episode un-certified, not
    un-judged: an escaping exception here would abort the whole delete decision and
    could be mistaken for "no mismatch found".
    """
    try:
        return check(source, converted)
    except Exception as bad:  # noqa: BLE001 — a check must never crash the decision
        return failed(name, f"unexpected error: {bad}")
