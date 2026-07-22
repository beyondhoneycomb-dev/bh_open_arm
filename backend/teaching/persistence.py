"""Atomic persistence for a per-arm teaching-point collection (WP-2D-05 file IO).

The collection file is the disk source of truth for an arm's taught postures, so a
torn write is a corrupt SoT. The write is persist-then-swap — write a sibling temp
file, flush and ``fsync`` it, ``os.replace`` onto the target, then ``fsync`` the
parent directory — which is POSIX-atomic: a reader sees either the whole previous
file or the whole new one, never a partial write, even across a mid-write kill.

This is the same discipline ``backend.calibration.atomic_io`` uses for the per-arm
zero record. That module's writer is bound to the ``OpenArmCalibration`` shape and its
frozen JSON Schema, so it cannot persist this different collection; the discipline is
reused, the schema-bound function is not. (The gripper mirror record resolves the same
question the same way — see ``backend.gripper_endpoint.persistence``.)

Loading validates every point before returning, so a hand-edited file whose point
dropped its zero provenance is refused at read time (acceptance ① on the load side)
rather than surfacing later as a posture replayed against no zero.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from backend.teaching.constants import COLLECTION_SUFFIX, COLLECTION_VERSION
from backend.teaching.point import TeachingPoint
from backend.teaching.store import TeachingPointStore


class TeachingCollectionError(ValueError):
    """Raised when a collection file violates the WP-2D-05 collection shape."""


def teaching_points_path_for(directory: Path, robot_id: str) -> Path:
    """Return the collection file path for a follower instance.

    Args:
        directory: The directory holding teaching-point collections.
        robot_id: The follower instance id.

    Returns:
        (Path) ``<directory>/<robot_id>.oa_teach.json``.
    """
    return directory / f"{robot_id}{COLLECTION_SUFFIX}"


def to_json_dict(store: TeachingPointStore) -> dict[str, Any]:
    """Return the collection as a JSON-ready object.

    Args:
        store: The store to serialise.

    Returns:
        (dict[str, Any]) ``{version, side, points: [...]}``.
    """
    return {
        "version": COLLECTION_VERSION,
        "side": store.side,
        "points": [point.to_json_dict() for point in store.points()],
    }


def save_teaching_points_atomic(path: Path, store: TeachingPointStore) -> None:
    """Write a teaching-point collection to disk atomically.

    Args:
        path: Destination collection file path.
        store: The store to persist.
    """
    body = json.dumps(to_json_dict(store), indent=2, sort_keys=True) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)  # noqa: PTH105 — atomic rename primitive; Path.replace only wraps it
        _fsync_dir(path.parent)
    except BaseException:
        # A failed write must not leave a stray temp file a later glob would pick up.
        tmp_path.unlink(missing_ok=True)
        raise


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so a rename into it is durable across a crash."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_teaching_points(path: Path) -> TeachingPointStore:
    """Read, validate, and return a teaching-point collection.

    Every point is rebuilt through ``TeachingPoint.from_json_dict``, so a point that
    dropped its zero provenance is refused here rather than loaded (acceptance ①). The
    store's own arm and uniqueness invariants are enforced as the points are seated.

    Args:
        path: The collection file path.

    Returns:
        (TeachingPointStore) The validated store.

    Raises:
        FileNotFoundError: If the file does not exist.
        TeachingCollectionError: If the collection envelope is malformed.
        TeachingPointError: If any point violates the frozen point shape.
    """
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TeachingCollectionError("collection file did not parse to an object")
    version = data.get("version")
    if version != COLLECTION_VERSION:
        raise TeachingCollectionError(
            f"collection version must be {COLLECTION_VERSION}, got {version!r}"
        )
    side = data.get("side")
    if not isinstance(side, str):
        raise TeachingCollectionError("collection is missing its arm 'side'")
    raw_points = data.get("points")
    if not isinstance(raw_points, list):
        raise TeachingCollectionError("collection 'points' must be a list")

    store = TeachingPointStore(side)
    points: list[TeachingPoint] = []
    for entry in raw_points:
        if not isinstance(entry, dict):
            raise TeachingCollectionError("each teaching point must be an object")
        points.append(TeachingPoint.from_json_dict(entry))
    store.replace_all(points)
    return store
