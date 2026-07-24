"""Legacy import + export block for OpenArm datasets (WP-3D-07, `02b` §8).

`openarm-dataset-convert` has exactly one valid use on this platform: importing a
legacy OpenArm dataset into LeRobot v3.0, in an isolated environment (`FR-DAT-040`).
Everything else this band does is a refusal or a display:

- **No export.** The converter's input is always OpenArm; there is no LeRobot-input
  path, so our own recordings cannot be converted back out (`FR-DAT-039`). And
  `--format gr00t` / `--format lerobot_v2.1` outputs are blocked — GR00T is a native
  LeRobot policy and v2.1 will not load under `lerobot >= 0.5` (`FR-DAT-042`). Both
  refusals run through one authorization point (`guard.evaluate_conversion`), so there
  is no code path that authorizes an export at all.
- **Isolated import.** The v3.0 import is composed as an isolated-environment
  invocation and never imported into this runtime (`isolation.py`).
- **Schema diff on display.** An imported artifact's schema differs subtly from a
  native recording — float64 `timestamp`, extra `success`/`last_frame_index` fields,
  `joint1..gripper` names — and that difference is rendered as data (`schema.py`).
- **No merge with native.** An imported artifact is tagged `IMPORTED_LEGACY`; the
  merge guard refuses to merge it with a native recording (`merge_guard.py`,
  `FR-DAT-041`).
- **Load validation.** An import whose `timestamp` grid is outside `1/fps ± 1e-4` is
  `INVALID` and never a training input (`importer.py`, `FR-DAT-043`).

The conversion transform itself is the external converter's job and is not
re-implemented here; this band owns only the policy, validation, diff and refusals.
"""

from __future__ import annotations

from backend.dataset.import_export.constants import (
    CONVERT_TOOL,
    CONVERTER_FORMAT_CHOICES,
    CONVERTER_MODULE,
    EXPORT_BLOCKED_FORMATS,
    IMPORT_ONLY_FORMAT,
    IMPORTED_NONSTANDARD_META_FIELDS,
    IMPORTED_TIMESTAMP_DTYPE,
    ISOLATED_ENV_EXTRA,
    ISOLATED_PYTHON_LOWER_BOUND,
    TIMESTAMP_INTERVAL_TOLERANCE_S,
)
from backend.dataset.import_export.formats import (
    FormatDisposition,
    InputKind,
    disposition_of,
    is_export_blocked,
    is_known_format,
)
from backend.dataset.import_export.guard import (
    ConversionDecision,
    ConversionRefusedError,
    ConversionRequest,
    ExportBlockedError,
    IsolatedInvocation,
    NoReversePathError,
    RefusalKind,
    UnsupportedOutputError,
    authorize_conversion,
    evaluate_conversion,
    plan_import,
)
from backend.dataset.import_export.importer import (
    ImportedDataset,
    ImportOutcome,
    LoadValidation,
    Validity,
    accept_imported_dataset,
    no_hub_upload_decision,
    validate_import_load,
)
from backend.dataset.import_export.isolation import (
    REQUIRED_ISOLATED_ENV,
    IsolatedEnv,
    IsolationBreachError,
    assert_converter_not_imported,
    converter_present_in_native_runtime,
    python_lower_bound_resolved,
)
from backend.dataset.import_export.merge_guard import (
    ImportNativeMergeError,
    MergeEligibility,
    assert_native_only_merge,
    merge_eligibility,
)
from backend.dataset.import_export.provenance import DatasetProvenance
from backend.dataset.import_export.schema import (
    SchemaDifference,
    SchemaFacts,
    diff_schemas,
    legacy_import_schema_facts,
    native_schema_facts,
    render_schema_diff,
)

__all__ = [
    "CONVERTER_FORMAT_CHOICES",
    "CONVERTER_MODULE",
    "CONVERT_TOOL",
    "EXPORT_BLOCKED_FORMATS",
    "IMPORTED_NONSTANDARD_META_FIELDS",
    "IMPORTED_TIMESTAMP_DTYPE",
    "IMPORT_ONLY_FORMAT",
    "ISOLATED_ENV_EXTRA",
    "ISOLATED_PYTHON_LOWER_BOUND",
    "REQUIRED_ISOLATED_ENV",
    "TIMESTAMP_INTERVAL_TOLERANCE_S",
    "ConversionDecision",
    "ConversionRefusedError",
    "ConversionRequest",
    "DatasetProvenance",
    "ExportBlockedError",
    "FormatDisposition",
    "ImportNativeMergeError",
    "ImportOutcome",
    "ImportedDataset",
    "InputKind",
    "IsolatedEnv",
    "IsolatedInvocation",
    "IsolationBreachError",
    "LoadValidation",
    "MergeEligibility",
    "NoReversePathError",
    "RefusalKind",
    "SchemaDifference",
    "SchemaFacts",
    "UnsupportedOutputError",
    "Validity",
    "accept_imported_dataset",
    "assert_converter_not_imported",
    "assert_native_only_merge",
    "authorize_conversion",
    "converter_present_in_native_runtime",
    "diff_schemas",
    "disposition_of",
    "evaluate_conversion",
    "is_export_blocked",
    "is_known_format",
    "legacy_import_schema_facts",
    "merge_eligibility",
    "native_schema_facts",
    "no_hub_upload_decision",
    "plan_import",
    "python_lower_bound_resolved",
    "render_schema_diff",
    "validate_import_load",
]
