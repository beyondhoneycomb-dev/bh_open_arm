"""Schema facts of a LeRobot dataset, and the native-vs-imported difference display.

`02b` §8.2 WP-3D-07 ③ requires an imported artifact to *show* that its schema is
subtly different from a native recording. This module reduces both families to the
same small `SchemaFacts` shape and diffs them, so the difference is presented as data
rather than asserted in prose. The native facts are derived from the frozen
`CTR-REC@v1` contract (never restated); the imported facts encode the reference
converter's known deviations (`FR-DAT-041`): float64 `timestamp`, extra
`success`/`last_frame_index` meta fields, and `joint1..gripper` channel names.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.dataset.import_export.constants import (
    IMPORTED_NONSTANDARD_META_FIELDS,
    IMPORTED_TIMESTAMP_DTYPE,
)
from backend.dataset.import_export.provenance import DatasetProvenance
from contracts.recorder import (
    META_FEATURES,
    MOTOR_NAMES,
    RecorderConfig,
    action_names,
    feature_set,
    observation_state_names,
)

# The `meta/info.json` feature key whose dtype forks between the families
# (native float32 vs imported float64). Named once so the derivation and the diff
# label agree.
TIMESTAMP_FEATURE_KEY = "timestamp"


@dataclass(frozen=True)
class SchemaFacts:
    """The schema axes that distinguish a native recording from a legacy import.

    Attributes:
        provenance: Whether the dataset was natively recorded or legacy-imported.
        fps: The frame rate the dataset's `timestamp` grid is built on.
        timestamp_dtype: The `timestamp` feature dtype (native float32 / imported
            float64).
        meta_fields: The `meta/info.json` meta feature keys present, in order.
        state_channel_names: The `observation.state` channel names.
        action_channel_names: The `action` channel names.
    """

    provenance: DatasetProvenance
    fps: int
    timestamp_dtype: str
    meta_fields: tuple[str, ...]
    state_channel_names: tuple[str, ...]
    action_channel_names: tuple[str, ...]


def native_schema_facts(config: RecorderConfig, fps: int) -> SchemaFacts:
    """Derive the native schema facts from the frozen `CTR-REC@v1` contract.

    Args:
        config: The recorder configuration the native dataset was produced under.
        fps: The dataset frame rate.

    Returns:
        (SchemaFacts) The native facts; nothing is restated — names, meta set and the
            `timestamp` dtype all come from the contract.
    """
    features = feature_set(config)
    timestamp_dtype = str(features[TIMESTAMP_FEATURE_KEY]["dtype"])
    return SchemaFacts(
        provenance=DatasetProvenance.NATIVE,
        fps=fps,
        timestamp_dtype=timestamp_dtype,
        meta_fields=tuple(META_FEATURES),
        state_channel_names=observation_state_names(
            config.bimanual, config.use_velocity_and_torque
        ),
        action_channel_names=action_names(config.bimanual),
    )


def _legacy_channel_names() -> tuple[str, ...]:
    """The legacy converter's single-arm channel names — `joint1..gripper`.

    The native motor keys carry an underscore (`joint_1`); the converter drops it
    (`FR-DAT-041`). Derived from `MOTOR_NAMES` so the two forms cannot silently
    diverge on anything but the underscore this models.

    Returns:
        (tuple[str, ...]) The legacy channel names.
    """
    return tuple(motor.replace("_", "") for motor in MOTOR_NAMES)


def legacy_import_schema_facts(fps: int) -> SchemaFacts:
    """Build the schema facts of a legacy v3.0 import (`FR-DAT-041`).

    The imported dataset carries float64 `timestamp`, the five LeRobot meta features
    plus `success`/`last_frame_index`, and `joint1..gripper` channel names.

    Args:
        fps: The dataset frame rate.

    Returns:
        (SchemaFacts) The imported facts, provenance `IMPORTED_LEGACY`.
    """
    channels = _legacy_channel_names()
    return SchemaFacts(
        provenance=DatasetProvenance.IMPORTED_LEGACY,
        fps=fps,
        timestamp_dtype=IMPORTED_TIMESTAMP_DTYPE,
        meta_fields=tuple(META_FEATURES) + IMPORTED_NONSTANDARD_META_FIELDS,
        state_channel_names=channels,
        action_channel_names=channels,
    )


@dataclass(frozen=True)
class SchemaDifference:
    """One axis on which two schemas differ.

    Attributes:
        axis: The schema axis label (e.g. `timestamp.dtype`, `meta.extra_fields`).
        native: The native value on this axis.
        imported: The imported value on this axis.
    """

    axis: str
    native: str
    imported: str


def diff_schemas(native: SchemaFacts, imported: SchemaFacts) -> tuple[SchemaDifference, ...]:
    """Compute the differences an imported schema shows against a native one.

    Args:
        native: The native reference schema.
        imported: The imported schema to compare.

    Returns:
        (tuple[SchemaDifference, ...]) One entry per differing axis, empty when the
            two are identical on every compared axis.
    """
    differences: list[SchemaDifference] = []

    if native.timestamp_dtype != imported.timestamp_dtype:
        differences.append(
            SchemaDifference(
                axis="timestamp.dtype",
                native=native.timestamp_dtype,
                imported=imported.timestamp_dtype,
            )
        )

    extra = tuple(field for field in imported.meta_fields if field not in native.meta_fields)
    if extra:
        differences.append(
            SchemaDifference(
                axis="meta.extra_fields",
                native="(none)",
                imported=", ".join(extra),
            )
        )

    if native.state_channel_names != imported.state_channel_names:
        differences.append(
            SchemaDifference(
                axis="observation.state.names",
                native=_names_summary(native.state_channel_names),
                imported=_names_summary(imported.state_channel_names),
            )
        )

    if native.action_channel_names != imported.action_channel_names:
        differences.append(
            SchemaDifference(
                axis="action.names",
                native=_names_summary(native.action_channel_names),
                imported=_names_summary(imported.action_channel_names),
            )
        )

    return tuple(differences)


def _names_summary(names: tuple[str, ...]) -> str:
    """Summarize a channel-name list as `first..last` for a compact diff cell.

    Args:
        names: The channel names.

    Returns:
        (str) `first..last` when there are two or more names, else the single name
            or `(empty)`.
    """
    if not names:
        return "(empty)"
    if len(names) == 1:
        return names[0]
    return f"{names[0]}..{names[-1]}"


def render_schema_diff(native: SchemaFacts, imported: SchemaFacts) -> str:
    """Render the native/imported schema difference as a display table.

    `02b` §8.2 WP-3D-07 ③: the imported artifact must show its schema difference. An
    empty diff renders an explicit "identical" line rather than a blank, so a reader
    never mistakes an unrun comparison for a clean one.

    Args:
        native: The native reference schema.
        imported: The imported schema.

    Returns:
        (str) A human-readable difference report.
    """
    differences = diff_schemas(native, imported)
    header = (
        f"schema diff: {imported.provenance.value} vs {native.provenance.value} "
        f"(fps={imported.fps})"
    )
    if not differences:
        return f"{header}\n  (schemas identical on every compared axis)"
    lines = [header]
    for difference in differences:
        lines.append(
            f"  {difference.axis}: native={difference.native} | imported={difference.imported}"
        )
    lines.append("  -> families must NOT merge (FR-DAT-041)")
    return "\n".join(lines)
