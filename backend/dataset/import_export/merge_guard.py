"""The merge guard — a legacy-imported dataset must never merge with a native one.

`FR-DAT-041`: an imported artifact's schema differs subtly from a native recording,
and the two families must not be merged into one dataset. This guard is the boundary
that refuses such a merge. It is intentionally strict: a merge is eligible only when
BOTH sides are natively recorded. Any legacy-imported participant is refused, because
mixing an imported family in — even with another imported one — reintroduces the
subtle-schema hazard the boundary exists to stop.

WP-3D-06 owns the merge operation and its shape-equality rule; this guard is the
family-provenance precondition WP-3D-06 (and the S-08 dataset screen) consults before
any merge, expressed on the `SchemaFacts` both bands already carry.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.dataset.import_export.provenance import DatasetProvenance
from backend.dataset.import_export.schema import SchemaFacts, diff_schemas


class ImportNativeMergeError(RuntimeError):
    """Raised when a merge would mix a legacy-imported dataset with a native one.

    `FR-DAT-041`: the two families have subtly different schemas and must stay apart.
    """


@dataclass(frozen=True)
class MergeEligibility:
    """Whether two datasets may be merged, and why.

    Attributes:
        ok: True only when both sides are natively recorded and schema-identical.
        reason: The justification for the verdict.
    """

    ok: bool
    reason: str


def merge_eligibility(left: SchemaFacts, right: SchemaFacts) -> MergeEligibility:
    """Decide whether two datasets are eligible to merge, without raising.

    A merge is eligible only when both sides are `NATIVE`. If either is
    `IMPORTED_LEGACY` the merge is refused on provenance alone; the schema diff is
    included in the reason so a caller can show *why* the families differ.

    Args:
        left: One dataset's schema facts.
        right: The other dataset's schema facts.

    Returns:
        (MergeEligibility) The verdict with its reason.
    """
    imported_sides = [
        facts for facts in (left, right) if facts.provenance is DatasetProvenance.IMPORTED_LEGACY
    ]
    if imported_sides:
        native_sides = [
            facts for facts in (left, right) if facts.provenance is DatasetProvenance.NATIVE
        ]
        reference = native_sides[0] if native_sides else left
        differences = diff_schemas(reference, imported_sides[0])
        axes = ", ".join(difference.axis for difference in differences) or "provenance"
        return MergeEligibility(
            ok=False,
            reason=(
                "refused: a legacy-imported dataset must not merge with a native one; "
                f"schemas differ on [{axes}] (FR-DAT-041)"
            ),
        )
    if left.state_channel_names != right.state_channel_names:
        return MergeEligibility(
            ok=False,
            reason="refused: native datasets differ in observation.state names",
        )
    return MergeEligibility(ok=True, reason="both datasets are native and schema-identical")


def assert_native_only_merge(left: SchemaFacts, right: SchemaFacts) -> None:
    """Refuse a merge that would mix a legacy-imported dataset with a native one.

    Args:
        left: One dataset's schema facts.
        right: The other dataset's schema facts.

    Raises:
        ImportNativeMergeError: When either side is legacy-imported.
    """
    eligibility = merge_eligibility(left, right)
    if not eligibility.ok:
        raise ImportNativeMergeError(eligibility.reason)
