"""WP-3D-07 ③: an imported artifact shows its schema diff vs native.

`02b` §8.2 WP-3D-07 ③ / `FR-DAT-041`: the imported schema differs subtly from a native
recording on three axes — float64 `timestamp`, extra `success`/`last_frame_index` meta
fields, and `joint1..gripper` channel names. This module checks the diff surfaces each,
that the render carries the no-merge warning, and that a native-vs-native comparison is
empty (so the diff is a real signal, not a constant).
"""

from __future__ import annotations

from backend.dataset.import_export import (
    IMPORTED_NONSTANDARD_META_FIELDS,
    diff_schemas,
    legacy_import_schema_facts,
    render_schema_diff,
)
from tests.wp3d07 import support


def test_diff_reports_timestamp_dtype_fork() -> None:
    """The diff shows native float32 vs imported float64 `timestamp` (`FR-DAT-041`)."""
    native = support.single_arm_native_facts()
    imported = legacy_import_schema_facts(fps=support.FIXTURE_FPS)
    axes = {d.axis: d for d in diff_schemas(native, imported)}
    assert axes["timestamp.dtype"].native == "float32"
    assert axes["timestamp.dtype"].imported == "float64"


def test_diff_reports_nonstandard_meta_fields() -> None:
    """The imported artifact's extra meta fields are surfaced (`FR-DAT-041`)."""
    native = support.single_arm_native_facts()
    imported = legacy_import_schema_facts(fps=support.FIXTURE_FPS)
    axes = {d.axis: d for d in diff_schemas(native, imported)}
    for field in IMPORTED_NONSTANDARD_META_FIELDS:
        assert field in axes["meta.extra_fields"].imported


def test_diff_reports_channel_naming_convention() -> None:
    """Native `joint_1..` vs imported `joint1..` naming is surfaced on both channels."""
    native = support.single_arm_native_facts()
    imported = legacy_import_schema_facts(fps=support.FIXTURE_FPS)
    axes = {d.axis for d in diff_schemas(native, imported)}
    assert "observation.state.names" in axes
    assert "action.names" in axes


def test_render_carries_no_merge_warning() -> None:
    """The rendered diff states the families must not merge (`FR-DAT-041`)."""
    native = support.native_facts()
    imported = legacy_import_schema_facts(fps=support.FIXTURE_FPS)
    text = render_schema_diff(native, imported)
    assert "must NOT merge" in text
    assert "FR-DAT-041" in text


def test_native_vs_native_diff_is_empty() -> None:
    """Two identical native schemas produce no differences — the diff is a real signal."""
    native = support.native_facts()
    assert diff_schemas(native, native) == ()
    assert "identical" in render_schema_diff(native, native)
