"""Merge preflight: feature-schema, fps and robot_type equality (WP-3D-06, `02b` §8.2).

`02b` §8.2 WP-3D-06 ① and `FR-DAT-044`: two datasets merge only when their feature
schema (every key, its dtype, its shape), their `fps`, and their `robot_type` are
identical. The load-bearing case is the `observation.state` shape: 24 vs 8 means
`use_velocity_and_torque` was on for one recording and off for the other, so the two
carry different channels and a merge would concatenate mismatched vectors — meaningless,
and refused with that specific diagnosis rather than a generic shape error.

The descriptor is read straight from `meta/info.json` as v3.0 storage (the WP-3D-01
direct-read convention, `06` §5.6); no LeRobot load and no `CTR-REC@v1` import is on
this path, so the equality check depends only on what is actually written to disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.dataset.merge.constants import (
    FEATURE_DTYPE_KEY,
    FEATURE_SHAPE_KEY,
    INFO_FEATURES_KEY,
    INFO_FPS_KEY,
    INFO_RELATIVE_PATH,
    INFO_ROBOT_TYPE_KEY,
    OBSERVATION_STATE_KEY,
)


class MergeSchemaError(ValueError):
    """Raised when two merge sources do not share an identical schema/fps/robot_type.

    Every case is a merge refusal (`02b` §8.2 WP-3D-06 ①): a differing feature key set,
    a per-feature dtype or shape mismatch, a differing `fps`, or a differing
    `robot_type`. The `observation.state` shape divergence is reported as the
    `use_velocity_and_torque` split it actually is, not as a bare shape mismatch.
    """


class MergeSchemaReadError(ValueError):
    """Raised when a source's `meta/info.json` cannot be read as a v3.0 descriptor.

    A source that carries no readable descriptor cannot be proven mergeable, so it is
    refused rather than merged on a guess.
    """


def _feature_dtype(body: Any) -> str | None:
    """Return a feature body's dtype, or None when it declares none (a meta feature)."""
    if isinstance(body, dict):
        value = body.get(FEATURE_DTYPE_KEY)
        return None if value is None else str(value)
    return None


def _feature_shape(body: Any) -> tuple[int, ...] | None:
    """Return a feature body's shape as an int tuple, or None when it declares none.

    Args:
        body: One `info.json` feature entry.

    Returns:
        (tuple[int, ...] | None) The shape, or None for a shapeless (meta) feature.
    """
    if not isinstance(body, dict):
        return None
    shape = body.get(FEATURE_SHAPE_KEY)
    if shape is None:
        return None
    if isinstance(shape, (list, tuple)):
        return tuple(int(dimension) for dimension in shape)
    return (int(shape),)


@dataclass(frozen=True)
class DatasetSchema:
    """The mergeability-relevant descriptor of one dataset, read from `info.json`.

    Attributes:
        repo_id: The dataset's identity, for diagnosis only (not compared).
        fps: The recording frame rate.
        robot_type: The declared robot type, or None when the descriptor omits it.
        feature_dtypes: Feature key to its dtype (None for a shapeless meta feature).
        feature_shapes: Feature key to its shape tuple (None for a meta feature).
    """

    repo_id: str
    fps: int
    robot_type: str | None
    feature_dtypes: dict[str, str | None]
    feature_shapes: dict[str, tuple[int, ...] | None]

    def observation_state_shape(self) -> tuple[int, ...] | None:
        """The `observation.state` shape — the vel/torque switch made visible.

        Returns:
            (tuple[int, ...] | None) The state shape, or None when absent.
        """
        return self.feature_shapes.get(OBSERVATION_STATE_KEY)

    @classmethod
    def from_root(cls, repo_id: str, root: Path) -> DatasetSchema:
        """Read a dataset's descriptor from `<root>/meta/info.json`.

        Args:
            repo_id: The dataset's identity, kept for diagnosis.
            root: The dataset root directory.

        Returns:
            (DatasetSchema) The descriptor read from disk.

        Raises:
            MergeSchemaReadError: When `info.json` is missing, malformed, or lacks the
                `features`/`fps` a mergeable descriptor must carry.
        """
        path = root / INFO_RELATIVE_PATH
        if not path.is_file():
            raise MergeSchemaReadError(f"{path} is missing; not a LeRobot v3.0 dataset directory")
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as bad:
            raise MergeSchemaReadError(f"{path} is not valid JSON: {bad}") from bad
        if not isinstance(info, dict) or INFO_FEATURES_KEY not in info or INFO_FPS_KEY not in info:
            raise MergeSchemaReadError(
                f"{path} lacks required {INFO_FEATURES_KEY!r}/{INFO_FPS_KEY!r}"
            )
        features = info[INFO_FEATURES_KEY]
        if not isinstance(features, dict):
            raise MergeSchemaReadError(f"{path} {INFO_FEATURES_KEY!r} is not a feature map")
        robot_type = info.get(INFO_ROBOT_TYPE_KEY)
        return cls(
            repo_id=repo_id,
            fps=int(info[INFO_FPS_KEY]),
            robot_type=None if robot_type is None else str(robot_type),
            feature_dtypes={key: _feature_dtype(body) for key, body in features.items()},
            feature_shapes={key: _feature_shape(body) for key, body in features.items()},
        )


def _check_state_shape(reference: DatasetSchema, other: DatasetSchema) -> None:
    """Refuse a merge whose `observation.state` shape diverged (the vel/torque split).

    Args:
        reference: The first source's schema.
        other: A later source's schema.

    Raises:
        MergeSchemaError: When the state shapes differ, named as the
            `use_velocity_and_torque` divergence it is.
    """
    reference_shape = reference.observation_state_shape()
    other_shape = other.observation_state_shape()
    if reference_shape != other_shape:
        raise MergeSchemaError(
            f"observation.state shape {other_shape} in {other.repo_id!r} differs from "
            f"{reference_shape} in {reference.repo_id!r}; a differing state width means "
            "use_velocity_and_torque diverged between the recordings, so the vectors carry "
            "different channels and the merge is meaningless (WP-3D-06 refused)"
        )


def _check_features(reference: DatasetSchema, other: DatasetSchema) -> None:
    """Refuse a merge whose feature key set, dtypes, or shapes differ.

    Args:
        reference: The first source's schema.
        other: A later source's schema.

    Raises:
        MergeSchemaError: On a differing key set, dtype, or shape.
    """
    reference_keys = set(reference.feature_dtypes)
    other_keys = set(other.feature_dtypes)
    if reference_keys != other_keys:
        only_reference = sorted(reference_keys - other_keys)
        only_other = sorted(other_keys - reference_keys)
        raise MergeSchemaError(
            f"feature key sets differ between {reference.repo_id!r} and {other.repo_id!r}: "
            f"only in first {only_reference}, only in second {only_other} (WP-3D-06 refused)"
        )
    for key in sorted(reference_keys):
        if reference.feature_dtypes[key] != other.feature_dtypes[key]:
            raise MergeSchemaError(
                f"feature {key!r} dtype {other.feature_dtypes[key]!r} in {other.repo_id!r} "
                f"differs from {reference.feature_dtypes[key]!r} in {reference.repo_id!r} "
                "(WP-3D-06 refused)"
            )
        if reference.feature_shapes[key] != other.feature_shapes[key]:
            raise MergeSchemaError(
                f"feature {key!r} shape {other.feature_shapes[key]} in {other.repo_id!r} "
                f"differs from {reference.feature_shapes[key]} in {reference.repo_id!r} "
                "(WP-3D-06 refused)"
            )


def verify_mergeable_schema(schemas: list[DatasetSchema]) -> DatasetSchema:
    """Verify every source shares one schema, fps and robot_type; return the shared one.

    The `observation.state` shape is checked first so the vel/torque divergence gets its
    named diagnosis before the generic per-feature comparison would report the same shape
    mismatch less usefully (`02b` §8.2 WP-3D-06 ①, `FR-DAT-044`).

    Args:
        schemas: The source schemas, in merge order; at least two.

    Returns:
        (DatasetSchema) The first schema, now proven equal to every other.

    Raises:
        MergeSchemaError: On the first divergence found, or when fewer than two sources
            are given (a merge needs at least two).
    """
    if len(schemas) < 2:
        raise MergeSchemaError(f"merge needs at least two sources, got {len(schemas)}")
    reference = schemas[0]
    for other in schemas[1:]:
        if reference.fps != other.fps:
            raise MergeSchemaError(
                f"fps {other.fps} in {other.repo_id!r} differs from {reference.fps} in "
                f"{reference.repo_id!r} (WP-3D-06 refused)"
            )
        if reference.robot_type != other.robot_type:
            raise MergeSchemaError(
                f"robot_type {other.robot_type!r} in {other.repo_id!r} differs from "
                f"{reference.robot_type!r} in {reference.repo_id!r} (WP-3D-06 refused)"
            )
        _check_state_shape(reference, other)
        _check_features(reference, other)
    return reference
