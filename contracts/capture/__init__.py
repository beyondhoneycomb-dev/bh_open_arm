"""CTR-CAP@v1 — the per-episode capture-timestamp sidecar contract.

The public surface of the capture contract. `schema.py` is the frozen body (the
sidecar shape, the grab-site attachment pin, the synthetic-grid fact, and the
offset/drift/continuity verifiers), mirrored language-agnostically in
`schema.json`. `attachment.py` is the static ban that catches a consumer stamping
receive time under the capture column (`02b` §5.2 WP-3A-02 ①). `reverify.py` re-runs
the sidecar checks over a capture fixture (`02b` §5.2 WP-3A-02 ③).

Everything time-, camera- and queue-shaped is consumed from `CTR-PRIM@v1` and never
restated here (`02b` §5.0b); the no-redefinition scan enforces that.
"""

from __future__ import annotations

from contracts.capture.attachment import (
    ConsumerAttachment,
    check_no_consumer_attachment,
    scan_module,
)
from contracts.capture.reverify import (
    ReverifyResult,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from contracts.capture.schema import (
    CAPTURE_MATCH_QUEUE,
    CAPTURE_TS_COLUMN_SUFFIX,
    CLOCK_SOURCE,
    CONSUMED_CONTRACT,
    CONTRACT_ID,
    EPISODE_INDEX_COLUMN,
    FRAME_INDEX_COLUMN,
    FRAME_NUMBER_COLUMN_SUFFIX,
    LEROBOT_TIMESTAMP_IS_SYNTHETIC,
    LEROBOT_TIMESTAMP_META_NOTE,
    SANCTIONED_ATTACHMENT_SITE,
    SCHEMA_VERSION,
    SENSOR_TS_COLUMN_SUFFIX,
    TIMESTAMP_UNIT_NS,
    AttachmentSite,
    CameraSlotKey,
    CaptureContractError,
    CaptureSidecar,
    CaptureSidecarRow,
    CaptureTimestamp,
    DropClassification,
    QueueSemantics,
    SensorSample,
    SlotCapture,
    SyntheticGridTimestamp,
    TimestampDomain,
    capture_match_drop_classification,
    capture_ts_column,
    frame_number_column,
    frame_numbers_continuous,
    host_sensor_offsets,
    lerobot_timestamp_meta,
    offset_drift_span,
    sensor_ts_column,
    sidecar_from_records,
    sidecar_to_records,
    slot_frame_numbers,
    slot_from_capture_ts_column,
    synthetic_grid_timestamp,
    validate_sidecar,
    verify_attachment_site,
)

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
    "ConsumerAttachment",
    "DropClassification",
    "QueueSemantics",
    "ReverifyResult",
    "SensorSample",
    "SlotCapture",
    "SyntheticGridTimestamp",
    "TimestampDomain",
    "capture_match_drop_classification",
    "capture_ts_column",
    "check_no_consumer_attachment",
    "fixture_dir_from_env",
    "frame_number_column",
    "frame_numbers_continuous",
    "host_sensor_offsets",
    "lerobot_timestamp_meta",
    "offset_drift_span",
    "reverify_from_fixture",
    "scan_module",
    "sensor_ts_column",
    "sidecar_from_records",
    "sidecar_to_records",
    "slot_frame_numbers",
    "slot_from_capture_ts_column",
    "synthetic_grid_timestamp",
    "validate_sidecar",
    "verify_attachment_site",
]
