"""The per-arm teaching-point collection (WP-2D-05, 02b §4 산출).

One store serves one arm. Left and right are separate instances holding separate
point lists, because their limits and zero offsets are asymmetric (mirror geometry):
a right posture is meaningless on the left arm and the store refuses to hold it
(acceptance ③). This is the backend expression of "left/right do not share one
widget instance" — two stores, side-tagged, never one shared list.

The store owns ordering and identity (points are unique by name within it) and the
CRUD/reorder/duplicate operations over that list. It deliberately exposes *no* method
that yields postures "for replay" without a current ``ZeroIdentity``: the only way to
obtain a replayable set is through the zero-match gate (``replay_verdicts`` and the
filters over it), so a posture cannot be replayed after a zero change without the gate
seeing it. That closed path is what makes the negative branch — silent replay after a
zero procedure change — unreachable rather than merely discouraged.
"""

from __future__ import annotations

from dataclasses import replace

from backend.teaching.constants import ARM_SIDES
from backend.teaching.point import TeachingPoint, TeachingPointError
from backend.teaching.zero_match import ReplayVerdict, ZeroIdentity, evaluate_replay


class TeachingStoreError(ValueError):
    """Raised on an illegal store operation (wrong arm, duplicate/absent name, bad order)."""


class TeachingPointStore:
    """An ordered, name-unique collection of one arm's teaching points."""

    def __init__(self, side: str) -> None:
        """Create an empty store for one arm.

        Args:
            side: "left" or "right"; the only arm this store holds points for.
        """
        if side not in ARM_SIDES:
            raise TeachingStoreError(f"side must be one of {ARM_SIDES}, got {side!r}")
        self._side = side
        self._points: list[TeachingPoint] = []

    @property
    def side(self) -> str:
        """The arm this store serves."""
        return self._side

    def points(self) -> tuple[TeachingPoint, ...]:
        """Return the points in their current order."""
        return tuple(self._points)

    def names(self) -> tuple[str, ...]:
        """Return the point names in their current order."""
        return tuple(point.name for point in self._points)

    def _index_of(self, name: str) -> int:
        """Return the list index of a named point, or raise if it is absent."""
        for index, point in enumerate(self._points):
            if point.name == name:
                return index
        raise TeachingStoreError(f"no teaching point named {name!r}")

    def get(self, name: str) -> TeachingPoint:
        """Return the point with this name.

        Raises:
            TeachingStoreError: If no point carries the name.
        """
        return self._points[self._index_of(name)]

    def add(self, point: TeachingPoint) -> None:
        """Append a point, refusing a wrong-arm or duplicate-name one.

        Args:
            point: The point to add; its ``arm_side`` must equal this store's side.

        Raises:
            TeachingStoreError: On an arm mismatch or a name already in the store.
        """
        if point.arm_side != self._side:
            raise TeachingStoreError(
                f"this is a {self._side} store; cannot hold a {point.arm_side} point"
            )
        if point.name in self.names():
            raise TeachingStoreError(f"a point named {point.name!r} already exists")
        self._points.append(point)

    def update(self, name: str, point: TeachingPoint) -> None:
        """Replace the named point in place, keeping its position.

        Args:
            name: The point to replace.
            point: The replacement; its side must match the store, and its name may
                only equal ``name`` or a name not otherwise present.

        Raises:
            TeachingStoreError: On an arm mismatch, an absent target, or a name that
                collides with a different existing point.
        """
        index = self._index_of(name)
        if point.arm_side != self._side:
            raise TeachingStoreError(
                f"this is a {self._side} store; cannot hold a {point.arm_side} point"
            )
        if point.name != name and point.name in self.names():
            raise TeachingStoreError(f"a point named {point.name!r} already exists")
        self._points[index] = point

    def remove(self, name: str) -> None:
        """Delete the named point.

        Raises:
            TeachingStoreError: If no point carries the name.
        """
        del self._points[self._index_of(name)]

    def reorder(self, order: tuple[str, ...]) -> None:
        """Reorder the points to match a permutation of their names.

        Args:
            order: Every current name exactly once, in the desired order.

        Raises:
            TeachingStoreError: If ``order`` is not a permutation of the current names.
        """
        if sorted(order) != sorted(self.names()):
            raise TeachingStoreError(
                "reorder requires exactly the current names, each once; "
                f"got {list(order)} against {list(self.names())}"
            )
        by_name = {point.name: point for point in self._points}
        self._points = [by_name[name] for name in order]

    def duplicate(self, name: str, new_name: str) -> TeachingPoint:
        """Append a copy of a point under a new name, keeping its zero provenance.

        The copy carries the same taught posture and the same zero provenance — it is
        the same physical pose under a second label — so it remains gated by the same
        zero identity as the original. Only the name changes; ``timestamp`` is kept as
        the copy records the posture it was taken from, not a fresh teaching event.

        Args:
            name: The point to copy.
            new_name: The copy's label; must not already exist.

        Returns:
            (TeachingPoint) The appended copy.

        Raises:
            TeachingStoreError: If the source is absent or ``new_name`` already exists.
        """
        source = self.get(name)
        if new_name in self.names():
            raise TeachingStoreError(f"a point named {new_name!r} already exists")
        try:
            copy = source.renamed(new_name)
        except TeachingPointError as exc:
            raise TeachingStoreError(str(exc)) from exc
        self._points.append(copy)
        return copy

    def replay_verdicts(self, current: ZeroIdentity) -> tuple[ReplayVerdict, ...]:
        """Gate every point against the current zero identity, in store order.

        This is the acceptance-② load-time check: given the robot's current zero
        record, each point is either replayable or blocked with a warning. It is the
        only door to replay — there is no method that yields postures without a current
        identity to check them against.

        Args:
            current: The robot's current zero identity for this store's arm.

        Returns:
            (tuple[ReplayVerdict, ...]) One verdict per point, in order.
        """
        return tuple(evaluate_replay(point, current) for point in self._points)

    def replayable(self, current: ZeroIdentity) -> tuple[TeachingPoint, ...]:
        """Return only the points the gate allows against the current zero identity."""
        return tuple(
            point
            for point, verdict in zip(self._points, self.replay_verdicts(current), strict=True)
            if verdict.allowed
        )

    def blocked(self, current: ZeroIdentity) -> tuple[tuple[TeachingPoint, ReplayVerdict], ...]:
        """Return the points the gate blocks, paired with their warning verdicts."""
        return tuple(
            (point, verdict)
            for point, verdict in zip(self._points, self.replay_verdicts(current), strict=True)
            if not verdict.allowed
        )

    def replace_all(self, points: list[TeachingPoint]) -> None:
        """Replace the whole point list, enforcing arm and uniqueness invariants.

        Used by the loader to seat a file's points into a fresh store. A point whose
        arm disagrees with the store, or a duplicate name, is refused here so a loaded
        collection is held to the same invariants as one built call by call.

        Args:
            points: The points to seat, in order.

        Raises:
            TeachingStoreError: On an arm mismatch or a duplicate name.
        """
        seen: set[str] = set()
        for point in points:
            if point.arm_side != self._side:
                raise TeachingStoreError(
                    f"this is a {self._side} store; cannot hold a {point.arm_side} point"
                )
            if point.name in seen:
                raise TeachingStoreError(f"duplicate point name in collection: {point.name!r}")
            seen.add(point.name)
        self._points = list(points)


def clone_store(store: TeachingPointStore) -> TeachingPointStore:
    """Return a deep copy of a store (points are immutable, so the list is copied)."""
    copy = TeachingPointStore(store.side)
    copy.replace_all([replace(point) for point in store.points()])
    return copy
