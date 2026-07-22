"""CTR-CAP@v1 — the per-episode capture-timestamp sidecar contract.

`02b` §5.1/§5.2 WP-3A-02 fixes what this module is the frozen body of: a camera
frame's *capture instant* is attached at the grab site and carried, per episode,
in a sidecar table that joins to the LeRobot dataset by `frame_index`. The one
rule the contract exists to protect is where the timestamp comes from — a
`capture_ts` is the moment the frame was grabbed, never the moment a GUI or
recorder received it. A consumer that stamps receive-time has erased the exposure
phase difference for good (`02b` §5.2 WP-3A-02 ①, the `FAIL_BLOCKING` branch); the
static ban that catches it lives in `contracts.capture.attachment`.

Everything time-shaped here is *consumed* from `CTR-PRIM@v1`, never restated
(`02b` §5.0b): the clock source and nanosecond unit, the `CaptureTimestamp` /
`SyntheticGridTimestamp` domain split, the `CameraSlotKey` grammar and its
`<slot>_capture_ts` column derivation, and the `capture_match` queue class whose
drop is a *counted* miss rather than a defect. A CAP that declared its own
timestamp domain would fork the primitive five ways; the no-redefinition scan
(`contracts.prim.check_no_redefinition`) is what makes that fork fail to build.

The four things the contract adds on top of those primitives:

1. The sidecar column set — `episode_index`, `frame_index`, and per-slot
   `<slot>_capture_ts` plus the *parallel* `<slot>_sensor_ts` / `<slot>_frame_number`
   a device that exposes a hardware clock and frame counter also preserves. The
   parallel columns never replace `capture_ts`; they sit beside it so host↔sensor
   offset, drift and frame-number continuity stay auditable (`02b` §5.2 ③).
2. The attachment-site pin — `SANCTIONED_ATTACHMENT_SITE = GRAB`. `capture_ts` may
   only be produced at the grab site; `verify_attachment_site` refuses any other,
   the runtime twin of the static ban.
3. The synthetic-grid fact — the LeRobot dataset `timestamp` is `frame_index / fps`,
   a playback grid orthogonal to capture time, and the contract marks it synthetic
   for the meta/UI so the two are never read as one (`02b` §5.2 WP-3A-02 ④).
4. The sidecar shape and its verifiers — one table per episode, `frame_index` the
   contiguous join key, with offset/drift and frame-number-continuity functions the
   quality path (`WP-3B-04`) runs over real capture data.

This module is `CONTRACT_FROZEN` once `WP-3A-06` freezes `CTR-CAP@v1`; until then it
is `DRAFT`. It imports only the light `contracts` lane, so consumers stay offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from contracts.prim import (
    CAPTURE_TS_COLUMN_SUFFIX,
    CLOCK_SOURCE,
    TIMESTAMP_UNIT_NS,
    CameraSlotKey,
    CaptureTimestamp,
    DropClassification,
    QueueSemantics,
    SyntheticGridTimestamp,
    TimestampDomain,
    slot_from_capture_ts_column,
)
from contracts.prim import CONTRACT_ID as PRIM_CONTRACT_ID
from contracts.prim import QUEUE_PROFILES as PRIM_QUEUE_PROFILES

# The contract id this module is the frozen body of. Freeze checks, staleness and
# the JSON-mirror cross-check key on this exact string, so it is named once.
CONTRACT_ID = "CTR-CAP@v1"

# The frozen generation. Widening the sidecar is `CTR-CAP@v2`, never an in-place
# edit of this literal (`06` §4.3, `CR-2`).
SCHEMA_VERSION = 1

# The single upstream this contract consumes by reference. Named so a bump of
# `CTR-PRIM@v1` propagates staleness here (`stale_on: CTR-PRIM:MAJOR_BUMP`).
CONSUMED_CONTRACT = PRIM_CONTRACT_ID


class CaptureContractError(ValueError):
    """Raised when a value violates the frozen CTR-CAP@v1 sidecar contract.

    Distinct from `PrimitiveRedefinitionError`: this guards the CAP-specific shape
    (sidecar columns, join key, attachment site), not a primitive's definition.
    """


# ---------------------------------------------------------------------------
# Sidecar columns
# ---------------------------------------------------------------------------

# The two per-episode join columns. `episode_index` is constant within one
# sidecar; `frame_index` is the contiguous 0-based row index that joins the
# sidecar to the dataset's frames (`02b` §5.2 WP-3A-02 ②).
EPISODE_INDEX_COLUMN = "episode_index"
FRAME_INDEX_COLUMN = "frame_index"

# The parallel-preservation column suffixes. A device that exposes a hardware
# timestamp and frame counter (e.g. RealSense) carries them beside `capture_ts`,
# never instead of it, so the two clocks can be diffed after the fact. The
# `capture_ts` column stem itself is `CTR-PRIM`'s `CAPTURE_TS_COLUMN_SUFFIX`.
SENSOR_TS_COLUMN_SUFFIX = "_sensor_ts"
FRAME_NUMBER_COLUMN_SUFFIX = "_frame_number"


def capture_ts_column(slot: CameraSlotKey) -> str:
    """The `<slot>_capture_ts` sidecar column carrying this slot's grab instant.

    Delegates to the primitive so the column stem has one definition (`CTR-PRIM`).

    Args:
        slot: The camera slot whose capture-timestamp column is named.

    Returns:
        (str) The capture-timestamp column name for the slot.
    """
    return slot.capture_ts_column()


def sensor_ts_column(slot: CameraSlotKey) -> str:
    """The `<slot>_sensor_ts` sidecar column carrying the device's hardware clock.

    Args:
        slot: The camera slot whose sensor-timestamp column is named.

    Returns:
        (str) The sensor-timestamp column name for the slot.
    """
    return f"{slot.value}{SENSOR_TS_COLUMN_SUFFIX}"


def frame_number_column(slot: CameraSlotKey) -> str:
    """The `<slot>_frame_number` sidecar column carrying the device's frame counter.

    Args:
        slot: The camera slot whose frame-number column is named.

    Returns:
        (str) The frame-number column name for the slot.
    """
    return f"{slot.value}{FRAME_NUMBER_COLUMN_SUFFIX}"


# ---------------------------------------------------------------------------
# Attachment site — capture_ts is produced at grab, never at receive
# ---------------------------------------------------------------------------


class AttachmentSite(StrEnum):
    """Where a `capture_ts` value was produced (`02b` §5.2 WP-3A-02 ①).

    `GRAB` is the moment the camera backend read the frame; `RECEIVE` is any later
    point a consumer got it (a queue pop, a WS deserialization). Only `GRAB`
    carries the exposure instant — a `RECEIVE` stamp is receive time wearing the
    capture column's name, which is the defect the contract forbids.
    """

    GRAB = "grab"
    RECEIVE = "receive"


# The pin: `capture_ts` may only be attached at the grab site. `WP-3B-01` (the
# camera backend) is the one sanctioned producer; every downstream contract is a
# consumer that reads the column, never writes it.
SANCTIONED_ATTACHMENT_SITE = AttachmentSite.GRAB


def verify_attachment_site(declared: AttachmentSite) -> None:
    """Refuse any attachment site other than the pinned grab site.

    The runtime twin of the `contracts.capture.attachment` static scan: a code path
    that declares it attaches `capture_ts` at receive time is rejected here rather
    than allowed to record a receive stamp under the capture column.

    Args:
        declared: The attachment site a producer declares.

    Raises:
        CaptureContractError: If `declared` is not `SANCTIONED_ATTACHMENT_SITE`.
    """
    if declared != SANCTIONED_ATTACHMENT_SITE:
        raise CaptureContractError(
            f"capture_ts must be attached at {SANCTIONED_ATTACHMENT_SITE.value} "
            f"(immediately after grab); a consumer attaching at {declared.value} is forbidden"
        )


# ---------------------------------------------------------------------------
# Capture-match drop semantics (consumed from CTR-PRIM)
# ---------------------------------------------------------------------------

# The queue class a capture-to-frame match uses (`CTR-PRIM` `QUEUE_PROFILES`). Its
# drop is COUNTED, not a DEFECT: a frame that cannot be matched to a capture row is
# dropped and tallied, never interpolated or duplicated (`WP-3B-04` reads this).
CAPTURE_MATCH_QUEUE = PRIM_QUEUE_PROFILES["capture_match"]


def capture_match_drop_classification() -> DropClassification:
    """The classification of a capture-match miss — a counted drop, by contract.

    Returns:
        (DropClassification) `COUNTED`: the miss is expected and tallied.
    """
    return CAPTURE_MATCH_QUEUE.drop_classification


# ---------------------------------------------------------------------------
# Synthetic playback grid (LeRobot `timestamp`)
# ---------------------------------------------------------------------------

# The LeRobot dataset `timestamp` column is `frame_index / fps` — a synthetic
# playback grid in seconds, orthogonal to when a frame was captured. The contract
# marks it synthetic so meta/UI never present it as a real capture time
# (`02b` §5.2 WP-3A-02 ④).
LEROBOT_TIMESTAMP_IS_SYNTHETIC = True
LEROBOT_TIMESTAMP_META_NOTE = (
    "dataset 'timestamp' is a synthetic frame_index/fps grid, not a capture instant; "
    "the real per-frame capture time lives in the CTR-CAP sidecar <slot>_capture_ts columns"
)


def synthetic_grid_timestamp(frame_index: int, fps: float) -> SyntheticGridTimestamp:
    """The LeRobot `timestamp` grid coordinate for a frame — `frame_index / fps`.

    Deliberately returns `CTR-PRIM`'s `SyntheticGridTimestamp`, not a
    `CaptureTimestamp`: the two are different domains and the type keeps a consumer
    from reading the synthetic grid as capture time.

    Args:
        frame_index: The 0-based frame position within the episode.
        fps: The dataset's frames-per-second grid rate.

    Returns:
        (SyntheticGridTimestamp) The synthetic playback-grid position in seconds.

    Raises:
        CaptureContractError: If `fps` is not positive.
    """
    if fps <= 0:
        raise CaptureContractError(f"fps must be positive to place the synthetic grid, got {fps}")
    return SyntheticGridTimestamp(seconds=frame_index / fps)


def lerobot_timestamp_meta() -> dict[str, object]:
    """The meta record that flags the dataset `timestamp` as a synthetic grid.

    Returns:
        (dict) The meta note the recorder writes and the UI shows (`02b` §5.2 ④).
    """
    return {
        "timestamp_domain": TimestampDomain.SYNTHETIC_GRID.value,
        "is_synthetic": LEROBOT_TIMESTAMP_IS_SYNTHETIC,
        "note": LEROBOT_TIMESTAMP_META_NOTE,
    }


# ---------------------------------------------------------------------------
# Sidecar shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SensorSample:
    """A device's parallel hardware timestamp and frame counter for one frame.

    Both fields are optional and independent: a plain webcam exposes neither, a
    RealSense exposes both. When present they are preserved beside `capture_ts`
    (never in place of it) so host↔sensor offset and frame-number continuity remain
    checkable (`02b` §5.2 WP-3A-02 ③).

    Attributes:
        sensor_ts_ns: The device hardware timestamp in nanoseconds, or None.
        frame_number: The device frame counter, or None.
    """

    sensor_ts_ns: int | None
    frame_number: int | None

    def __post_init__(self) -> None:
        """Reject non-integer hardware values."""
        if self.sensor_ts_ns is not None and (
            not isinstance(self.sensor_ts_ns, int) or isinstance(self.sensor_ts_ns, bool)
        ):
            raise CaptureContractError("sensor_ts_ns must be int ns or None")
        if self.frame_number is not None and (
            not isinstance(self.frame_number, int) or isinstance(self.frame_number, bool)
        ):
            raise CaptureContractError("frame_number must be int or None")


@dataclass(frozen=True)
class SlotCapture:
    """One camera slot's capture record for one frame.

    Attributes:
        capture_ts: The grab-time capture instant (`CTR-PRIM` `CaptureTimestamp`).
        sensor: The device's parallel hardware sample, or None when unavailable.
    """

    capture_ts: CaptureTimestamp
    sensor: SensorSample | None

    def __post_init__(self) -> None:
        """Reject a capture record whose timestamp is not a real capture instant."""
        if not isinstance(self.capture_ts, CaptureTimestamp):
            raise CaptureContractError(
                "SlotCapture.capture_ts must be a CTR-PRIM CaptureTimestamp "
                "(a grab instant), not a synthetic grid or raw int"
            )


@dataclass(frozen=True)
class CaptureSidecarRow:
    """One frame's row in the sidecar: its join index and every slot's capture.

    Attributes:
        frame_index: The 0-based frame position; the sidecar-to-dataset join key.
        slots: Capture record per camera slot, keyed by the shared slot identity.
    """

    frame_index: int
    slots: dict[CameraSlotKey, SlotCapture]

    def __post_init__(self) -> None:
        """Reject a negative index or an empty row."""
        if not isinstance(self.frame_index, int) or isinstance(self.frame_index, bool):
            raise CaptureContractError("frame_index must be an int")
        if self.frame_index < 0:
            raise CaptureContractError(f"frame_index must be >= 0, got {self.frame_index}")
        if not self.slots:
            raise CaptureContractError("a sidecar row must record at least one camera slot")


@dataclass(frozen=True)
class CaptureSidecar:
    """One episode's capture-timestamp sidecar (`02b` §5.2 WP-3A-02 ②).

    The sidecar is per episode. Its `frame_index` values are the contiguous
    sequence `0..N-1`, which is exactly the dataset frame index they join on, and
    every row records the same set of camera slots so the columns are rectangular.

    Attributes:
        episode_index: The episode this sidecar belongs to.
        rows: The per-frame rows, in ascending frame order.
    """

    episode_index: int
    rows: tuple[CaptureSidecarRow, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Enforce the per-episode, contiguous-`frame_index`, rectangular shape."""
        if not isinstance(self.episode_index, int) or isinstance(self.episode_index, bool):
            raise CaptureContractError("episode_index must be an int")
        if self.episode_index < 0:
            raise CaptureContractError(f"episode_index must be >= 0, got {self.episode_index}")
        expected = list(range(len(self.rows)))
        actual = [row.frame_index for row in self.rows]
        if actual != expected:
            raise CaptureContractError(
                f"frame_index must be the contiguous join key 0..{len(self.rows) - 1}, got {actual}"
            )
        if self.rows:
            slot_set = set(self.rows[0].slots)
            for row in self.rows[1:]:
                if set(row.slots) != slot_set:
                    raise CaptureContractError(
                        "every sidecar row must record the same camera slots "
                        "so the sidecar columns are rectangular"
                    )

    def slots(self) -> tuple[CameraSlotKey, ...]:
        """The camera slots this sidecar carries, in a stable order.

        Returns:
            (tuple[CameraSlotKey, ...]) The slot keys, sorted by value.
        """
        if not self.rows:
            return ()
        return tuple(sorted(self.rows[0].slots, key=lambda key: key.value))

    @staticmethod
    def join_key() -> str:
        """The column a sidecar joins to the dataset on.

        Returns:
            (str) `frame_index` — the contiguous per-episode join key.
        """
        return FRAME_INDEX_COLUMN


def validate_sidecar(sidecar: CaptureSidecar) -> CaptureSidecar:
    """Validate a sidecar against the frozen contract, returning it on success.

    Construction already enforces the structural invariants; this is the named
    entry point a reverify hook and the tests call, and the place a future
    cross-column rule would attach.

    Args:
        sidecar: The sidecar to validate.

    Returns:
        (CaptureSidecar) The same sidecar, once validated.

    Raises:
        CaptureContractError: If the sidecar violates the contract.
    """
    if not isinstance(sidecar, CaptureSidecar):
        raise CaptureContractError("validate_sidecar expects a CaptureSidecar")
    return sidecar


# ---------------------------------------------------------------------------
# Serialization — the per-episode sidecar table as flat records
# ---------------------------------------------------------------------------


def sidecar_to_records(sidecar: CaptureSidecar) -> list[dict[str, int]]:
    """Flatten a sidecar to one wide record per frame (the parquet row shape).

    Each record carries `episode_index`, `frame_index`, and, per slot, the
    `<slot>_capture_ts` value plus `<slot>_sensor_ts` / `<slot>_frame_number` when
    the device supplied them. Absent hardware values are omitted rather than zeroed.

    Args:
        sidecar: The sidecar to flatten.

    Returns:
        (list[dict[str, int]]) One record per frame, in frame order.
    """
    records: list[dict[str, int]] = []
    for row in sidecar.rows:
        record: dict[str, int] = {
            EPISODE_INDEX_COLUMN: sidecar.episode_index,
            FRAME_INDEX_COLUMN: row.frame_index,
        }
        for slot, capture in row.slots.items():
            record[capture_ts_column(slot)] = capture.capture_ts.mono_ns
            if capture.sensor is not None:
                if capture.sensor.sensor_ts_ns is not None:
                    record[sensor_ts_column(slot)] = capture.sensor.sensor_ts_ns
                if capture.sensor.frame_number is not None:
                    record[frame_number_column(slot)] = capture.sensor.frame_number
        records.append(record)
    return records


def sidecar_from_records(episode_index: int, records: list[dict[str, int]]) -> CaptureSidecar:
    """Rebuild a sidecar from its flat per-frame records, then validate it.

    The slot set is recovered from the `<slot>_capture_ts` columns via the primitive
    inverse, so the same grammar that wrote the columns reads them back.

    Args:
        episode_index: The episode the records belong to.
        records: Flat per-frame records, as produced by `sidecar_to_records`.

    Returns:
        (CaptureSidecar) The reconstructed, validated sidecar.

    Raises:
        CaptureContractError: If a record is malformed or the shape is invalid.
    """
    rows: list[CaptureSidecarRow] = []
    for record in records:
        if record.get(EPISODE_INDEX_COLUMN) != episode_index:
            raise CaptureContractError(
                f"record {EPISODE_INDEX_COLUMN} {record.get(EPISODE_INDEX_COLUMN)!r} "
                f"does not match sidecar episode {episode_index}"
            )
        frame_index = record[FRAME_INDEX_COLUMN]
        slots: dict[CameraSlotKey, SlotCapture] = {}
        for column, value in record.items():
            if not column.endswith(CAPTURE_TS_COLUMN_SUFFIX):
                continue
            slot = slot_from_capture_ts_column(column)
            sensor_ts = record.get(sensor_ts_column(slot))
            frame_number = record.get(frame_number_column(slot))
            sensor = (
                SensorSample(sensor_ts_ns=sensor_ts, frame_number=frame_number)
                if sensor_ts is not None or frame_number is not None
                else None
            )
            slots[slot] = SlotCapture(capture_ts=CaptureTimestamp(mono_ns=value), sensor=sensor)
        rows.append(CaptureSidecarRow(frame_index=frame_index, slots=slots))
    rows.sort(key=lambda row: row.frame_index)
    return validate_sidecar(CaptureSidecar(episode_index=episode_index, rows=tuple(rows)))


# ---------------------------------------------------------------------------
# Host↔sensor offset / drift and frame-number continuity (02b §5.2 WP-3A-02 ③)
# ---------------------------------------------------------------------------


def host_sensor_offsets(sidecar: CaptureSidecar, slot: CameraSlotKey) -> list[int]:
    """Per-frame host-minus-sensor clock offset for a slot, where both are known.

    The offset is `capture_ts - sensor_ts` in nanoseconds. Rows without a hardware
    timestamp contribute nothing, so a plain webcam yields an empty series rather
    than a fabricated zero.

    Args:
        sidecar: The episode sidecar.
        slot: The camera slot to measure.

    Returns:
        (list[int]) Host↔sensor offsets in nanoseconds, in frame order.
    """
    offsets: list[int] = []
    for row in sidecar.rows:
        capture = row.slots.get(slot)
        if capture is None or capture.sensor is None or capture.sensor.sensor_ts_ns is None:
            continue
        offsets.append(capture.capture_ts.mono_ns - capture.sensor.sensor_ts_ns)
    return offsets


def offset_drift_span(offsets: list[int]) -> int:
    """The peak-to-peak drift of a host↔sensor offset series.

    Args:
        offsets: Host↔sensor offsets from `host_sensor_offsets`.

    Returns:
        (int) `max - min` in nanoseconds, or 0 for a series shorter than two.
    """
    if len(offsets) < 2:
        return 0
    return max(offsets) - min(offsets)


def slot_frame_numbers(sidecar: CaptureSidecar, slot: CameraSlotKey) -> list[int]:
    """The device frame-counter series for a slot, where the device supplies it.

    Args:
        sidecar: The episode sidecar.
        slot: The camera slot to read.

    Returns:
        (list[int]) Frame numbers in frame order, skipping frames without one.
    """
    numbers: list[int] = []
    for row in sidecar.rows:
        capture = row.slots.get(slot)
        if capture is None or capture.sensor is None or capture.sensor.frame_number is None:
            continue
        numbers.append(capture.sensor.frame_number)
    return numbers


def frame_numbers_continuous(numbers: list[int]) -> bool:
    """Whether a device frame-counter series increments by exactly one each step.

    A gap means the device dropped frames between two we kept — the discontinuity
    the quality path must surface rather than hide (`02b` §5.2 WP-3A-02 ③).

    Args:
        numbers: A frame-number series from `slot_frame_numbers`.

    Returns:
        (bool) True when every consecutive pair differs by one; True for < 2 items.
    """
    return all(later - earlier == 1 for earlier, later in zip(numbers, numbers[1:], strict=False))


# The names a consuming schema must obtain from `CTR-PRIM` rather than restate; a
# CAP that binds any of these at module level has forked a primitive. Re-exported
# so a downstream reader imports the timestamp/camera/queue surface from the single
# primitive point through this contract.
__all__ = [
    "CAPTURE_MATCH_QUEUE",
    "CAPTURE_TS_COLUMN_SUFFIX",
    "CLOCK_SOURCE",
    "CONSUMED_CONTRACT",
    "CONTRACT_ID",
    "EPISODE_INDEX_COLUMN",
    "FRAME_INDEX_COLUMN",
    "FRAME_NUMBER_COLUMN_SUFFIX",
    "LEROBOT_TIMESTAMP_IS_SYNTHETIC",
    "LEROBOT_TIMESTAMP_META_NOTE",
    "SANCTIONED_ATTACHMENT_SITE",
    "SCHEMA_VERSION",
    "SENSOR_TS_COLUMN_SUFFIX",
    "TIMESTAMP_UNIT_NS",
    "AttachmentSite",
    "CameraSlotKey",
    "CaptureContractError",
    "CaptureSidecar",
    "CaptureSidecarRow",
    "CaptureTimestamp",
    "DropClassification",
    "QueueSemantics",
    "SensorSample",
    "SlotCapture",
    "SyntheticGridTimestamp",
    "TimestampDomain",
    "capture_match_drop_classification",
    "capture_ts_column",
    "frame_number_column",
    "frame_numbers_continuous",
    "host_sensor_offsets",
    "lerobot_timestamp_meta",
    "offset_drift_span",
    "sensor_ts_column",
    "sidecar_from_records",
    "sidecar_to_records",
    "slot_frame_numbers",
    "slot_from_capture_ts_column",
    "synthetic_grid_timestamp",
    "validate_sidecar",
    "verify_attachment_site",
]
