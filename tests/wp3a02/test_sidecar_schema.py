"""WP-3A-02 ② — the sidecar is per-episode and joins the dataset by frame_index.

`02b` §5.2 WP-3A-02 ② requires the capture sidecar to be created per episode and
joined on `frame_index`. These tests fix the shape: one sidecar per episode, a
contiguous `frame_index` join key, rectangular slot columns, a lossless flatten to
records and back, and a JSON mirror that does not drift from the Python surface.
The camera-identifier grammar and the timestamp type are consumed from `CTR-PRIM`,
so the sidecar column stems are the primitive's, not the contract's.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import contracts.capture as cap

SCHEMA_JSON = Path(__file__).resolve().parents[2] / "contracts" / "capture" / "schema.json"


def _json() -> dict:
    """Load the language-agnostic JSON mirror of the contract."""
    return json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))


def _sidecar(episode_index: int, frames: int) -> cap.CaptureSidecar:
    """Build a two-slot sidecar with a device slot and a plain slot."""
    left = cap.CameraSlotKey("left_wrist")
    scene = cap.CameraSlotKey("scene")
    rows = tuple(
        cap.CaptureSidecarRow(
            frame_index=i,
            slots={
                left: cap.SlotCapture(
                    cap.CaptureTimestamp(1_000 + i * 100),
                    cap.SensorSample(sensor_ts_ns=900 + i * 100, frame_number=10 + i),
                ),
                scene: cap.SlotCapture(cap.CaptureTimestamp(2_000 + i * 100), None),
            },
        )
        for i in range(frames)
    )
    return cap.CaptureSidecar(episode_index=episode_index, rows=rows)


def test_join_key_is_frame_index() -> None:
    """The sidecar joins to the dataset on `frame_index`, the primitive-free join column."""
    assert cap.CaptureSidecar.join_key() == cap.FRAME_INDEX_COLUMN == "frame_index"


def test_sidecar_is_per_episode_and_records_its_episode() -> None:
    """A sidecar carries exactly one episode index for all its rows."""
    sidecar = _sidecar(episode_index=7, frames=4)
    assert sidecar.episode_index == 7
    for record in cap.sidecar_to_records(sidecar):
        assert record[cap.EPISODE_INDEX_COLUMN] == 7


def test_frame_index_must_be_the_contiguous_join_key() -> None:
    """A gap in `frame_index` breaks the join and is rejected at construction."""
    left = cap.CameraSlotKey("left_wrist")
    rows = (
        cap.CaptureSidecarRow(0, {left: cap.SlotCapture(cap.CaptureTimestamp(1), None)}),
        cap.CaptureSidecarRow(2, {left: cap.SlotCapture(cap.CaptureTimestamp(2), None)}),
    )
    with pytest.raises(cap.CaptureContractError):
        cap.CaptureSidecar(episode_index=0, rows=rows)


def test_rows_must_be_rectangular_across_slots() -> None:
    """Every frame records the same slots, or the sidecar columns are ragged."""
    left = cap.CameraSlotKey("left_wrist")
    scene = cap.CameraSlotKey("scene")
    rows = (
        cap.CaptureSidecarRow(
            0,
            {
                left: cap.SlotCapture(cap.CaptureTimestamp(1), None),
                scene: cap.SlotCapture(cap.CaptureTimestamp(2), None),
            },
        ),
        cap.CaptureSidecarRow(1, {left: cap.SlotCapture(cap.CaptureTimestamp(3), None)}),
    )
    with pytest.raises(cap.CaptureContractError):
        cap.CaptureSidecar(episode_index=0, rows=rows)


def test_records_round_trip_is_lossless() -> None:
    """Flattening to records and back recovers the identical sidecar."""
    sidecar = _sidecar(episode_index=3, frames=5)
    records = cap.sidecar_to_records(sidecar)
    assert records[0][cap.capture_ts_column(cap.CameraSlotKey("left_wrist"))] == 1_000
    assert cap.sidecar_from_records(3, records) == sidecar


def test_parallel_columns_are_preserved_beside_capture_ts() -> None:
    """A device slot carries sensor_ts and frame_number columns beside capture_ts."""
    sidecar = _sidecar(episode_index=0, frames=2)
    left = cap.CameraSlotKey("left_wrist")
    scene = cap.CameraSlotKey("scene")
    record = cap.sidecar_to_records(sidecar)[0]
    assert cap.capture_ts_column(left) in record
    assert cap.sensor_ts_column(left) in record
    assert cap.frame_number_column(left) in record
    # The plain slot has a capture_ts but no parallel hardware columns.
    assert cap.capture_ts_column(scene) in record
    assert cap.sensor_ts_column(scene) not in record


def test_slot_columns_reuse_the_primitive_grammar() -> None:
    """The `<slot>_capture_ts` stem is CTR-PRIM's, and its inverse recovers the slot."""
    left = cap.CameraSlotKey("left_wrist")
    column = cap.capture_ts_column(left)
    assert column == "left_wrist_capture_ts"
    assert column.endswith(cap.CAPTURE_TS_COLUMN_SUFFIX)
    assert cap.slot_from_capture_ts_column(column) == left


def test_capture_record_rejects_a_non_capture_timestamp() -> None:
    """A SlotCapture must hold a real CaptureTimestamp, not a raw int or synthetic grid."""
    with pytest.raises(cap.CaptureContractError):
        cap.SlotCapture(capture_ts=1234, sensor=None)  # type: ignore[arg-type]
    with pytest.raises(cap.CaptureContractError):
        cap.SlotCapture(capture_ts=cap.SyntheticGridTimestamp(0.1), sensor=None)  # type: ignore[arg-type]


def test_validate_sidecar_returns_the_sidecar() -> None:
    """The named validator accepts a well-formed sidecar and returns it."""
    sidecar = _sidecar(episode_index=1, frames=3)
    assert cap.validate_sidecar(sidecar) is sidecar


def test_consumed_contract_is_ctr_prim() -> None:
    """CTR-CAP consumes exactly CTR-PRIM@v1 by reference."""
    assert cap.CONSUMED_CONTRACT == "CTR-PRIM@v1"
    assert cap.CONTRACT_ID == "CTR-CAP@v1"
    assert cap.SCHEMA_VERSION == 1


def test_json_mirror_agrees_with_python_surface() -> None:
    """The JSON mirror declares the same contract as the Python body."""
    doc = _json()
    assert doc["contract"] == cap.CONTRACT_ID
    assert doc["schema_version"] == cap.SCHEMA_VERSION
    assert doc["consumed_contract"] == cap.CONSUMED_CONTRACT

    columns = doc["columns"]
    assert columns["episode_index"]["name"] == cap.EPISODE_INDEX_COLUMN
    assert columns["frame_index"]["name"] == cap.FRAME_INDEX_COLUMN
    assert columns["frame_index"]["is_join_key"] is True
    assert columns["capture_ts"]["clock_source"] == cap.CLOCK_SOURCE
    assert columns["capture_ts"]["unit"] == cap.TIMESTAMP_UNIT_NS
    assert columns["sensor_ts"]["suffix"] == cap.SENSOR_TS_COLUMN_SUFFIX
    assert columns["frame_number"]["suffix"] == cap.FRAME_NUMBER_COLUMN_SUFFIX

    assert doc["attachment_site"]["sanctioned"] == cap.SANCTIONED_ATTACHMENT_SITE.value
    assert doc["attachment_site"]["forbidden"] == cap.AttachmentSite.RECEIVE.value
    assert doc["lerobot_timestamp"]["is_synthetic"] is cap.LEROBOT_TIMESTAMP_IS_SYNTHETIC
    assert doc["lerobot_timestamp"]["domain"] == cap.TimestampDomain.SYNTHETIC_GRID.value
    assert (
        doc["capture_match_queue"]["drop_classification"]
        == cap.capture_match_drop_classification().value
    )
