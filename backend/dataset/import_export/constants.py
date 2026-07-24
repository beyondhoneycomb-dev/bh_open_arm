"""Named constants for the WP-3D-07 legacy-import + export-block band (`02b` §8).

Every literal that carries policy meaning is named here so the guard code and the
regression tests speak the same vocabulary. The facts are drawn from `08` §2.2/§2.3
and `FR-DAT-039`~`043`:

- `openarm-dataset-convert` selects its OUTPUT with `--format`; its INPUT is always
  an OpenArm-layout dataset (`08` §2.2). There is no LeRobot-input path, so there is
  no export of our own recordings (`FR-DAT-039`).
- The one valid use of the tool is the legacy OpenArm -> LeRobot v3.0 import, run in
  an isolated environment (`FR-DAT-040`).
- `--format gr00t` / `--format lerobot_v2.1` outputs are blocked: GR00T is a native
  LeRobot policy so no v2.1 conversion is needed, and v2.1 will not load under
  `lerobot >= 0.5` (`FR-DAT-042`).
- The imported artifact's schema differs subtly from a native recording — float64
  `timestamp`, extra `success`/`last_frame_index` meta fields, `joint1..gripper`
  channel names — and the two families must never merge (`FR-DAT-041`).
"""

from __future__ import annotations

# The reference converter this band wraps by policy. It is never imported into the
# native runtime; it runs only inside the isolated import environment below.
CONVERT_TOOL = "openarm-dataset-convert"

# The importable module name of the reference converter (`08` §2.2:
# `openarm_dataset.Dataset`). The native runtime must NOT be able to import it —
# that absence is the runtime evidence of environment isolation (`isolation.py`).
CONVERTER_MODULE = "openarm_dataset"

# The `--format` output tokens the reference CLI offers (`convert.py:35-40`,
# `08` §2.2). Declared as the closed choice set so the CLI and the guard agree on
# exactly which values exist before deciding which are permitted.
FORMAT_OPENARM = "openarm"
FORMAT_LEROBOT_V21 = "lerobot_v2.1"
FORMAT_LEROBOT_V30 = "lerobot_v3.0"
FORMAT_GROOT = "gr00t"
CONVERTER_FORMAT_CHOICES = (FORMAT_OPENARM, FORMAT_LEROBOT_V21, FORMAT_LEROBOT_V30, FORMAT_GROOT)

# The single output format this platform accepts — the one-way legacy import
# (`FR-DAT-040`). Any other output is either blocked or not an import.
IMPORT_ONLY_FORMAT = FORMAT_LEROBOT_V30

# The output formats whose production is refused (`FR-DAT-042`). GR00T trains
# directly on our v3.0 dataset (`--policy.type=groot`), so a `gr00t` conversion is
# unnecessary; v2.1 raises `BackwardCompatibilityError` under `lerobot >= 0.5`, so
# producing it is pointless. Both are `M` requirements, not preferences.
EXPORT_BLOCKED_FORMATS = (FORMAT_GROOT, FORMAT_LEROBOT_V21)

# The isolated environment the import runs in (`FR-DAT-040`): the extra that pulls
# the v3.0 dataset writer.
ISOLATED_ENV_EXTRA = "openarm_dataset[lerobot-dataset-v3-0]"

# The Python lower bound of the isolated import environment is UNRESOLVED. `08`
# §2.9 / `NFR-REC-007` leave it undetermined pending lerobot's `requires-python`
# confirmed from source; `07`/`08`'s `>= 3.12` assumption is uncorroborated. `None`
# records the gap honestly rather than fabricating a bound (`FR-DAT-040`).
ISOLATED_PYTHON_LOWER_BOUND: str | None = None

# The load-validation tolerance for an imported artifact (`FR-DAT-043`): each
# consecutive `timestamp` gap must be within `1/fps ± tolerance_s`. Outside it the
# artifact is INVALID.
TIMESTAMP_INTERVAL_TOLERANCE_S = 1e-4

# The imported converter's `timestamp` dtype (`FR-DAT-041`,
# `openarm_dataset/lerobot_v30.py`): float64, against a native float32. Named as an
# external fact; the native dtype is derived from the frozen contract, not restated.
IMPORTED_TIMESTAMP_DTYPE = "float64"

# The non-standard meta fields the converter adds beyond the five LeRobot defaults
# (`FR-DAT-041`). Their presence is one axis of the native/imported schema diff.
IMPORTED_NONSTANDARD_META_FIELDS = ("success", "last_frame_index")
