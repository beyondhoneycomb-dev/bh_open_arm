"""Test doubles for the WP-OPS-04 guards — a recording uploader, a fixed clock, a
map-backed port probe.

Named functor classes rather than lambdas/closures so each double is a nameable
type the type checker and the reader can both see, and so a call count is a plain
attribute rather than mutable state captured in a closure.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from ops.hubguard.audit import UploadTarget


class RecordingUploader:
    """An `Uploader` that records every call instead of touching the network."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, UploadTarget]] = []

    def __call__(self, dataset: str, target: UploadTarget) -> None:
        self.calls.append((dataset, target))

    @property
    def count(self) -> int:
        """Number of times an upload was performed."""
        return len(self.calls)


class FixedClock:
    """A clock returning one fixed instant, for a deterministic audit `when`."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def __call__(self) -> datetime:
        return self._moment


class MapProbe:
    """A `PortProbe` that reports a fixed set of ports as already held."""

    def __init__(self, busy_ports: Iterable[int]) -> None:
        self._busy = frozenset(busy_ports)

    def __call__(self, host: str, port: int) -> bool:
        return port in self._busy
