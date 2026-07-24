"""WP-3D-06 ① — merge refuses any schema, fps or robot_type divergence.

`02b` §8.2 WP-3D-06 ① / `FR-DAT-044`: two datasets merge only when their feature schema
(keys, dtype, shape), `fps` and `robot_type` are identical. The `observation.state` shape
divergence (24 vs 8) is the `use_velocity_and_torque` split and gets its own diagnosis.
"""

from __future__ import annotations

import pytest

from backend.dataset.merge.schema import DatasetSchema, MergeSchemaError, verify_mergeable_schema


def _schema(
    repo_id: str,
    fps: int = 30,
    robot_type: str | None = None,
    state_shape: tuple[int, ...] = (48,),
    action_dtype: str = "float32",
) -> DatasetSchema:
    """Build a minimal but realistic dataset schema for the equality checks."""
    return DatasetSchema(
        repo_id=repo_id,
        fps=fps,
        robot_type=robot_type,
        feature_dtypes={
            "action": action_dtype,
            "observation.state": "float32",
            "timestamp": "float32",
            "episode_index": "int64",
        },
        feature_shapes={
            "action": (16,),
            "observation.state": state_shape,
            "timestamp": None,
            "episode_index": None,
        },
    )


def test_identical_schemas_accepted() -> None:
    """Two identical descriptors merge, and the shared schema is returned."""
    shared = verify_mergeable_schema([_schema("a"), _schema("b")])
    assert shared.observation_state_shape() == (48,)


def test_state_shape_divergence_named_as_velocity_torque() -> None:
    """24 vs 8 is refused as the use_velocity_and_torque split, not a bare shape error."""
    with pytest.raises(MergeSchemaError, match="use_velocity_and_torque"):
        verify_mergeable_schema([_schema("a", state_shape=(48,)), _schema("b", state_shape=(16,))])


def test_fps_mismatch_refused() -> None:
    """A differing fps refuses the merge."""
    with pytest.raises(MergeSchemaError, match="fps"):
        verify_mergeable_schema([_schema("a", fps=30), _schema("b", fps=60)])


def test_robot_type_mismatch_refused() -> None:
    """A differing robot_type refuses the merge."""
    with pytest.raises(MergeSchemaError, match="robot_type"):
        verify_mergeable_schema(
            [_schema("a", robot_type="openarm"), _schema("b", robot_type="other")]
        )


def test_feature_dtype_mismatch_refused() -> None:
    """A per-feature dtype divergence refuses the merge."""
    with pytest.raises(MergeSchemaError, match="dtype"):
        verify_mergeable_schema(
            [_schema("a", action_dtype="float32"), _schema("b", action_dtype="float64")]
        )


def test_feature_key_set_mismatch_refused() -> None:
    """A differing feature key set refuses the merge."""
    extra = _schema("b")
    extra.feature_dtypes["observation.images.left"] = "video"
    extra.feature_shapes["observation.images.left"] = (3, 8, 8)
    with pytest.raises(MergeSchemaError, match="feature key sets differ"):
        verify_mergeable_schema([_schema("a"), extra])


def test_single_source_refused() -> None:
    """A merge needs at least two sources."""
    with pytest.raises(MergeSchemaError, match="at least two"):
        verify_mergeable_schema([_schema("a")])
