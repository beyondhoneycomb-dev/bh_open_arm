"""Accepting a legacy-imported artifact — load validation, provenance, schema diff.

The conversion itself is done by `openarm-dataset-convert` inside the isolated
environment (`guard.plan_import`); this module handles what happens on OUR side once
the artifact exists: it is load-validated (`FR-DAT-043`), tagged as legacy-imported so
the merge guard can refuse it (`FR-DAT-041`), and diffed against the native schema for
display (`02b` §8.2 WP-3D-07 ③).

Load validation is the `FR-DAT-043` core: a `LeRobotDataset` load must succeed once and
every `timestamp` gap must fall within `1/fps ± tolerance_s`. An artifact that fails is
`INVALID` and is never exposed as a training input (`02b` §8.2 WP-3D-07 ④ / the batch
`INTEGRITY READY = 100%` invariant). Nothing about the import path pushes to the Hub;
the `WP-OPS-04` guard is reused to make that explicit rather than assumed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from backend.dataset.import_export.constants import TIMESTAMP_INTERVAL_TOLERANCE_S
from backend.dataset.import_export.provenance import DatasetProvenance
from backend.dataset.import_export.schema import (
    SchemaDifference,
    SchemaFacts,
    diff_schemas,
)
from ops.hubguard.push_policy import RecordConfigView, UploadDecision, resolve_push_to_hub


class Validity(Enum):
    """The load-validation verdict on an imported artifact.

    Attributes:
        VALID: The load check passed; the artifact may be used.
        INVALID: The load check failed; the artifact is never a training input.
    """

    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class LoadValidation:
    """The result of the `FR-DAT-043` load check on an imported artifact.

    Attributes:
        validity: VALID only when the timestamp grid is within tolerance.
        reason: Why the verdict was reached.
        worst_interval_error: The largest absolute deviation of a consecutive
            `timestamp` gap from `1/fps`, in seconds.
        tolerance_s: The tolerance the check was run at.
    """

    validity: Validity
    reason: str
    worst_interval_error: float
    tolerance_s: float


def validate_import_load(
    timestamps: Sequence[float],
    fps: int,
    tolerance_s: float = TIMESTAMP_INTERVAL_TOLERANCE_S,
) -> LoadValidation:
    """Validate an imported artifact's `timestamp` grid (`FR-DAT-043`).

    Each consecutive gap must be within `1/fps ± tolerance_s`. A dataset with fewer
    than two frames has no interval to check and is treated as invalid, because a
    load that yields no verifiable grid cannot be certified.

    Args:
        timestamps: The imported dataset's per-frame `timestamp` values, in order.
        fps: The dataset frame rate; must be positive.
        tolerance_s: The permitted deviation of a gap from `1/fps`.

    Returns:
        (LoadValidation) The verdict with the worst observed interval error.

    Raises:
        ValueError: When `fps` is not positive — the expected interval is undefined.
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive to define an expected interval; got {fps}")
    if len(timestamps) < 2:
        return LoadValidation(
            validity=Validity.INVALID,
            reason=f"only {len(timestamps)} frame(s); no interval to validate",
            worst_interval_error=float("inf"),
            tolerance_s=tolerance_s,
        )

    expected = 1.0 / fps
    worst = 0.0
    for previous, current in zip(timestamps, timestamps[1:], strict=False):
        error = abs((current - previous) - expected)
        worst = max(worst, error)

    if worst <= tolerance_s:
        return LoadValidation(
            validity=Validity.VALID,
            reason=f"timestamp gaps within 1/fps ± {tolerance_s} (worst {worst:.3e}s)",
            worst_interval_error=worst,
            tolerance_s=tolerance_s,
        )
    return LoadValidation(
        validity=Validity.INVALID,
        reason=(
            f"timestamp gap deviates {worst:.3e}s from 1/fps, over tolerance {tolerance_s} "
            "(FR-DAT-043)"
        ),
        worst_interval_error=worst,
        tolerance_s=tolerance_s,
    )


@dataclass(frozen=True)
class ImportedDataset:
    """A legacy-imported artifact as it exists on our side, ready to be accepted.

    Attributes:
        schema: The imported schema facts (provenance must be `IMPORTED_LEGACY`).
        timestamps: The per-frame `timestamp` values for load validation.
    """

    schema: SchemaFacts
    timestamps: tuple[float, ...]


@dataclass(frozen=True)
class ImportOutcome:
    """The full result of accepting an imported artifact.

    Attributes:
        provenance: Always `IMPORTED_LEGACY` — the tag the merge guard reads.
        validity: The load-validation verdict.
        load: The load-validation detail.
        schema_diff: The differences against the native reference schema.
        push_decision: The reused `WP-OPS-04` decision, always non-pushing here.
    """

    provenance: DatasetProvenance
    validity: Validity
    load: LoadValidation
    schema_diff: tuple[SchemaDifference, ...]
    push_decision: UploadDecision


def no_hub_upload_decision() -> UploadDecision:
    """Resolve the `WP-OPS-04` push decision for the import path — always non-pushing.

    The import never uploads to the Hub. Reusing the hub guard (rather than asserting
    it in prose) makes that a checked property: an unspecified `push_to_hub` resolves
    to `False` through the one enforcement point (`ops.hubguard.push_policy`).

    Returns:
        (UploadDecision) The enforced non-pushing decision.
    """
    return resolve_push_to_hub(RecordConfigView(push_to_hub=None), None)


def accept_imported_dataset(
    imported: ImportedDataset,
    native_reference: SchemaFacts,
    tolerance_s: float = TIMESTAMP_INTERVAL_TOLERANCE_S,
) -> ImportOutcome:
    """Accept a legacy-imported artifact: load-validate, tag, diff, and refuse upload.

    Args:
        imported: The imported artifact on our side.
        native_reference: The native schema to diff the import against.
        tolerance_s: The load-validation tolerance.

    Returns:
        (ImportOutcome) The verdict, load detail, schema diff and push decision.

    Raises:
        ValueError: When the artifact is not tagged `IMPORTED_LEGACY` — accepting a
            native dataset through the import path would erase the family boundary.
    """
    if imported.schema.provenance is not DatasetProvenance.IMPORTED_LEGACY:
        raise ValueError(
            "accept_imported_dataset requires an IMPORTED_LEGACY artifact; "
            f"got provenance {imported.schema.provenance.value}"
        )
    load = validate_import_load(imported.timestamps, imported.schema.fps, tolerance_s)
    schema_diff = diff_schemas(native_reference, imported.schema)
    return ImportOutcome(
        provenance=DatasetProvenance.IMPORTED_LEGACY,
        validity=load.validity,
        load=load,
        schema_diff=schema_diff,
        push_decision=no_hub_upload_decision(),
    )
