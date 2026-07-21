"""The tick trace — the audit channel and the evidence for the acceptance gates.

Every tick records one `TickRecord`: its index, the send time, the emission label,
the reason code, and the MIT batch that was written. This is the `executedMitCommand`
audit channel (`02a` §3.1 ⑥) and the trace of all four labels plus reason codes
(acceptance ⑨) at once — full, never sampled.

Two sinks implement the same `TraceSink` protocol:

- `TickTrace` keeps every record. It is what the label/lag/interval assertions read
  (acceptance ③④⑤⑧⑨), and it is the honest default.
- `TallyTrace` keeps counts and running extrema instead of a million dataclasses.
  A full trace is what ⑨ demands, but the million-tick invariant run (①) does not
  need to *store* a million frames to prove none was empty — the scheduler asserts
  the one-write-per-tick invariant inline. So the long runs use the tally, and the
  correctness runs use the full trace; neither weakens what the other proves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from backend.actuation.emissions import EmissionLabel, ReasonCode
from contracts.action import ExecutedMitCommand


@dataclass(frozen=True)
class TickRecord:
    """One tick's audit record.

    Attributes:
        index: Monotonic tick number from torque-on.
        at: Clock reading when the frame was written, in seconds.
        label: The emission label this tick.
        reason: The reason code this tick.
        batch: The MIT batch written — the `executedMitCommand` audit payload.
    """

    index: int
    at: float
    label: EmissionLabel
    reason: ReasonCode
    batch: tuple[ExecutedMitCommand, ...]


class TraceSink(Protocol):
    """A destination for per-tick records, written once per tick."""

    def record(self, entry: TickRecord) -> None:
        """Accept one tick's record.

        Args:
            entry: The record to append or fold in.
        """
        ...


@dataclass
class TickTrace:
    """A full, unsampled trace: every record kept in order."""

    entries: list[TickRecord] = field(default_factory=list)

    def record(self, entry: TickRecord) -> None:
        """Append a record.

        Args:
            entry: The tick record to keep.
        """
        self.entries.append(entry)

    def labels(self) -> set[EmissionLabel]:
        """Return the set of labels seen.

        Returns:
            (set[EmissionLabel]) Distinct labels across the trace.
        """
        return {entry.label for entry in self.entries}

    def reason_codes(self) -> set[ReasonCode]:
        """Return the set of reason codes seen.

        Returns:
            (set[ReasonCode]) Distinct reason codes across the trace.
        """
        return {entry.reason for entry in self.entries}

    def count(self, label: EmissionLabel) -> int:
        """Count records carrying a given label.

        Args:
            label: Label to count.

        Returns:
            (int) Number of ticks with that label.
        """
        return sum(1 for entry in self.entries if entry.label == label)

    def max_send_interval(self) -> float:
        """Return the longest gap between two consecutive CAN sends.

        Every tick sends exactly one frame, so this is the largest spacing between
        consecutive record timestamps. With fewer than two records there is no
        interval and the result is 0.0.

        Returns:
            (float) Longest inter-send interval, in seconds.
        """
        if len(self.entries) < 2:
            return 0.0
        return max(
            later.at - earlier.at
            for earlier, later in zip(self.entries, self.entries[1:], strict=False)
        )


@dataclass
class TallyTrace:
    """A counting sink for long runs: counts and extrema, not per-tick records."""

    ticks: int = 0
    label_counts: dict[EmissionLabel, int] = field(default_factory=dict)
    reasons: set[ReasonCode] = field(default_factory=set)
    _last_at: float | None = None
    max_interval: float = 0.0

    def record(self, entry: TickRecord) -> None:
        """Fold one record into the running counts and extrema.

        Args:
            entry: The tick record to account for.
        """
        self.ticks += 1
        self.label_counts[entry.label] = self.label_counts.get(entry.label, 0) + 1
        self.reasons.add(entry.reason)
        if self._last_at is not None:
            self.max_interval = max(self.max_interval, entry.at - self._last_at)
        self._last_at = entry.at

    def labels(self) -> set[EmissionLabel]:
        """Return the set of labels seen.

        Returns:
            (set[EmissionLabel]) Distinct labels folded in.
        """
        return set(self.label_counts)
