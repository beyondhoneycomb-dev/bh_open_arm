"""Named layout and policy constants for the merge/split band (WP-3D-06, `02b` §8).

The values here are the `meta/info.json` keys a merge equality check joins on, the
gain-profile tag's on-disk location, and the split/eval policy literals `02b` §8.2
WP-3D-06 fixes the behaviour with. They are not tunable thresholds: the acceptance
(shape/`fps`/`robot_type` equality, gain-profile equality, episode-boundary splits,
the `eval_steps`/`eval_split` block) fixes the *behaviour*, and these are the concrete
names it is expressed in.

The `info.json` keys are consumed as the LeRobot v3.0 storage convention, read as data
rather than imported from a schema — the same direct-read path the viewer (WP-3D-01)
takes (`06` §5.6). They are storage-layout strings, not `CTR-PRIM@v1` primitives, so
naming them here forks no contract.
"""

from __future__ import annotations

# `meta/info.json` — the dataset descriptor a merge reads its feature set, fps and
# robot type from. Read directly as v3.0 storage, never through a LeRobot import.
INFO_RELATIVE_PATH = "meta/info.json"
INFO_FEATURES_KEY = "features"
INFO_FPS_KEY = "fps"
INFO_ROBOT_TYPE_KEY = "robot_type"

# The two feature-body keys a merge compares per feature. Shape divergence is the
# load-bearing one: `observation.state` 24 vs 8 means `use_velocity_and_torque`
# diverged and the merge is meaningless (`02b` §8.2 WP-3D-06 ①).
FEATURE_DTYPE_KEY = "dtype"
FEATURE_SHAPE_KEY = "shape"

# The `observation.state` feature key whose shape carries the vel/torque switch. A
# storage-layout key (the viewer defines the same string), not a redefined primitive.
OBSERVATION_STATE_KEY = "observation.state"

# The gain-profile tag every mergeable dataset carries (`FR-DAT-045`). Its absence on
# any merge source is the gain-tagless FAIL_BLOCKING defect (`02b` §8.2 WP-3D-06 ②):
# gain drives the following-error distribution, so an untagged dataset could silently
# mix distributions.
GAIN_PROFILE_RELATIVE_PATH = "meta/gain_profile.json"

# The gain-profile tag's fields. `kp`/`kd` are the follower PD vectors that actually
# drive the following error; the profile id alone is not enough, because two datasets
# both tagged `custom` with different vectors are still distinct distributions.
GAIN_PROFILE_ID_FIELD = "profile_id"
GAIN_PROFILE_KP_FIELD = "kp"
GAIN_PROFILE_KD_FIELD = "kd"

# The DM MIT encoding bounds the follower PD gains are validated against (`03` §2.8,
# `FR-MOT-025`: `kp ∈ [0, 500]`, `kd ∈ [0, 5]`). A tag carrying an out-of-band gain
# never came from a real profile, so it is refused rather than merged.
GAIN_KP_MIN = 0.0
GAIN_KP_MAX = 500.0
GAIN_KD_MIN = 0.0
GAIN_KD_MAX = 5.0

# The tolerance two gain vectors must agree within to count as the same profile. The
# vectors are stored rounded, so this only absorbs float round-trip noise, not a real
# stiffness difference (the smallest real profile gap is J5 `24` vs `10`, `03` §3.4).
GAIN_MATCH_TOLERANCE = 1e-6

# The split-ratio sum a ratio split must reach, and the tolerance it may miss it by.
# Ratios that do not sum to one leave episodes unassigned or double-assigned, which is
# not an episode-boundary partition (`02b` §8.2 WP-3D-06 ③).
SPLIT_RATIO_SUM = 1.0
SPLIT_RATIO_TOLERANCE = 1e-9

# LeRobot's `dataset.eval_split` default (`configs/train.py`), the held-out fraction a
# training run carves per task. Distinct from a physical `split` (`FR-DAT-048`): one is
# a dataset partition on disk, the other a training-time holdout. `0.0` with
# `eval_steps > 0` is the combination blocked before training (`FR-DAT-049`).
DEFAULT_EVAL_SPLIT = 0.0
