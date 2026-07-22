"""In-process recorder embed (WP-3B-11).

The embedded equivalent of `lerobot record`: it drives `LeRobotDataset` through
the observe→act→send→add-frame loop in *this* process, never by spawning the
console script (which reconnects the robot every call and destroys its zero
calibration — `02b` §6.2 WP-3B-11). Four invariants define it:

- the `record_loop()` runs in-process, proven by a static scan that no process is
  spawned (`staticcheck`, acceptance ①);
- the `events` dict is owned by the backend (`RecordEvents`), driven by S-07's
  buttons rather than a `pynput`/TTY key listener (acceptance ②);
- a re-record clears the episode buffer without saving, so the episode index is
  not advanced (acceptance ④); and
- `finalize()` runs in a `finally` on every exit path — normal, exception, and
  interruption — because a missing parquet footer invalidates the whole dataset
  (acceptance ③).

`action` stays position-only (`CTR-REC@v1`): frames sample the `action` vector
from the `.pos` channel names alone, so a `.vel`/`.torque` value cannot enter it.
Camera streams are integrated at 3C; this package records `action` and
`observation.state` over the synthetic fixtures.
"""

from __future__ import annotations

from backend.recorder.embed.constants import (
    EVAL_NAME_PREFIX,
    EVENT_KEYS,
    EXIT_EARLY_KEY,
    RERECORD_EPISODE_KEY,
    STOP_RECORDING_KEY,
    TASK_KEY,
)
from backend.recorder.embed.dataset import (
    RecorderNameError,
    create_features,
    create_record_dataset,
    reject_eval_name,
    resolve_rgb_encoder,
    stamp_repo_id,
)
from backend.recorder.embed.events import RecordEvents
from backend.recorder.embed.loop import (
    FrameSchema,
    RecorderFpsMismatchError,
    RecordRobot,
    TeleopSource,
    build_record_frame,
    frame_schema,
    record_loop,
)
from backend.recorder.embed.session import (
    RecordResult,
    RecordSpec,
    record_session,
)
from backend.recorder.embed.staticcheck import scan_source, scan_tree

__all__ = [
    "EVAL_NAME_PREFIX",
    "EVENT_KEYS",
    "EXIT_EARLY_KEY",
    "FrameSchema",
    "RERECORD_EPISODE_KEY",
    "STOP_RECORDING_KEY",
    "TASK_KEY",
    "RecordEvents",
    "RecordResult",
    "RecordSpec",
    "RecordRobot",
    "RecorderFpsMismatchError",
    "RecorderNameError",
    "TeleopSource",
    "build_record_frame",
    "create_features",
    "create_record_dataset",
    "frame_schema",
    "record_loop",
    "record_session",
    "reject_eval_name",
    "resolve_rgb_encoder",
    "scan_source",
    "scan_tree",
    "stamp_repo_id",
]
