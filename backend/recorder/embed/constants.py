"""Named literals for the in-process recorder embed (WP-3B-11).

Every value here carries a decision the recorder embed depends on: the exact
event-dict keys LeRobot's `record_loop()` indexes, the dataset-name prefix the
tool reserves for policy evaluation, the `add_frame` task key, and the stamp
format that makes each session's `repo_id` unique. They are named so the one
place they are decided is findable.
"""

from __future__ import annotations

# The three episode-control flags LeRobot's `record_loop()` reads from its
# `events` dict (`utils/keyboard_input.py`: `init_keyboard_listener`). The embed
# owns that dict in the backend instead of a key listener, so these key names must
# stay byte-identical to LeRobot's — `record_loop()` subscripts them literally.
EXIT_EARLY_KEY = "exit_early"
RERECORD_EPISODE_KEY = "rerecord_episode"
STOP_RECORDING_KEY = "stop_recording"
EVENT_KEYS = (EXIT_EARLY_KEY, RERECORD_EPISODE_KEY, STOP_RECORDING_KEY)

# The per-frame task key `LeRobotDataset.add_frame` requires on every frame
# (`lerobot_record.record_loop`: `frame = {..., "task": single_task}`).
TASK_KEY = "task"

# The dataset-name prefix reserved for policy evaluation. `lerobot-record` refuses
# it because an `eval_` dataset is produced by `lerobot-rollout`, not by data
# collection; the embed enforces the same refusal (WP-3B-11 acceptance ⑥).
EVAL_NAME_PREFIX = "eval_"

# The separator between the account and the dataset name in a `repo_id`; the
# reserved-prefix check applies to the dataset-name half only.
REPO_ID_SEPARATOR = "/"

# The suffix stamped onto a `repo_id` at creation so each session is unique
# (mirrors `DatasetRecordConfig.stamp_repo_id`, which cannot be constructed on a
# host whose default video codec is unavailable). One underscore, then this
# `strftime` pattern (WP-3B-11 acceptance ⑤).
REPO_ID_STAMP_FORMAT = "%Y%m%d_%H%M%S"
REPO_ID_STAMP_JOINER = "_"
