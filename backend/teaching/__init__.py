"""Teaching-point schema and the zero-match replay gate (WP-2D-05).

``point`` is the frozen per-posture record; ``zero_match`` is the gate that permits a
replay only when the robot's current zero reference is the one a point was taught
against (the contract of 02b §4.2); ``store`` is the per-arm CRUD/reorder/duplicate
collection; ``persistence`` is its atomic file IO. The zero record itself is reused
from ``backend.calibration`` — this package adds the postures that depend on it and
the gate that keeps a taught posture from replaying against a changed zero.
"""

from __future__ import annotations

from backend.teaching.constants import (
    ARM_SIDES,
    COLLECTION_SUFFIX,
    COLLECTION_VERSION,
    EE_POSE_WIDTH,
    Q_URDF_WIDTH,
)
from backend.teaching.persistence import (
    TeachingCollectionError,
    load_teaching_points,
    save_teaching_points_atomic,
    teaching_points_path_for,
    to_json_dict,
)
from backend.teaching.point import TeachingPoint, TeachingPointError
from backend.teaching.store import TeachingPointStore, TeachingStoreError, clone_store
from backend.teaching.zero_match import (
    ReplayDecision,
    ReplayVerdict,
    ZeroIdentity,
    capture_teaching_point,
    evaluate_replay,
)

__all__ = [
    "ARM_SIDES",
    "COLLECTION_SUFFIX",
    "COLLECTION_VERSION",
    "EE_POSE_WIDTH",
    "Q_URDF_WIDTH",
    "ReplayDecision",
    "ReplayVerdict",
    "TeachingCollectionError",
    "TeachingPoint",
    "TeachingPointError",
    "TeachingPointStore",
    "TeachingStoreError",
    "ZeroIdentity",
    "capture_teaching_point",
    "clone_store",
    "evaluate_replay",
    "load_teaching_points",
    "save_teaching_points_atomic",
    "teaching_points_path_for",
    "to_json_dict",
]
