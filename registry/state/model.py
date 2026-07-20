"""Work-package state vocabulary and the legal-transition table.

The five states are canonical in `00` §3.3 / `02a` §-2.3 (WP-BOOT-04 acceptance ①) and are
written there in Korean. Code uses English identifiers; `KOREAN_LABEL` carries the canonical
spelling so reports can quote the plan without re-translating it at each call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkPackageState(StrEnum):
    """State of a single work package inside the execution store."""

    NOT_STARTED = "not_started"
    ACTIVE = "active"
    INTEGRATED = "integrated"
    STALE = "stale"
    CANCELLED = "cancelled"


KOREAN_LABEL: dict[WorkPackageState, str] = {
    WorkPackageState.NOT_STARTED: "미착수",
    WorkPackageState.ACTIVE: "활성",
    WorkPackageState.INTEGRATED: "통합됨",
    WorkPackageState.STALE: "stale",
    WorkPackageState.CANCELLED: "취소됨",
}

# Closed table. Anything absent is rejected; the exclusions below are load-bearing, not gaps:
#   INTEGRATED -> CANCELLED  merged work is undone by a named revert WP, never by cancellation
#                            (`05` §5.2 P-4 states cancellation and revert are distinct
#                            procedures, so collapsing them here would lose the distinction).
#   INTEGRATED -> ACTIVE     an integrated package re-opens only by first being marked stale by
#                            a gate flip (`05` §5.2 P-3), which is what authorises the re-run.
#   CANCELLED  -> *          terminal. A cancelled package is replaced by a *newly named* WP
#                            (`05` §5.2 P-6), so resurrection would erase that naming.
#   NOT_STARTED -> STALE     staleness stamps artifacts (`05` §5.2 P-3); a package that never
#                            ran has none. Its blocking is done by the gate check, not by state.
LEGAL_TRANSITIONS: frozenset[tuple[WorkPackageState, WorkPackageState]] = frozenset(
    {
        (WorkPackageState.NOT_STARTED, WorkPackageState.ACTIVE),
        (WorkPackageState.NOT_STARTED, WorkPackageState.CANCELLED),
        (WorkPackageState.ACTIVE, WorkPackageState.INTEGRATED),
        (WorkPackageState.ACTIVE, WorkPackageState.STALE),
        (WorkPackageState.ACTIVE, WorkPackageState.CANCELLED),
        (WorkPackageState.INTEGRATED, WorkPackageState.STALE),
        (WorkPackageState.STALE, WorkPackageState.ACTIVE),
        (WorkPackageState.STALE, WorkPackageState.CANCELLED),
    }
)

# A package still holding un-integrated output: cancellation enumerates exactly these
# (`02a` §-2.3 WP-BOOT-04 acceptance ⑦ — integrated output must not be enumerated).
CANCELLABLE_STATES: frozenset[WorkPackageState] = frozenset(
    {WorkPackageState.NOT_STARTED, WorkPackageState.ACTIVE, WorkPackageState.STALE}
)


class IllegalTransitionError(Exception):
    """Raised when a transition is not in `LEGAL_TRANSITIONS`.

    Also raised by the store when the observed previous state does not match the caller's
    expectation, which is how a concurrency loser is reported.
    """

    def __init__(self, wp: str, previous: WorkPackageState, new: WorkPackageState) -> None:
        super().__init__(f"{wp}: illegal transition {previous.value} -> {new.value}")
        self.wp = wp
        self.previous = previous
        self.new = new


def is_legal(previous: WorkPackageState, new: WorkPackageState) -> bool:
    """Report whether a transition is permitted.

    Args:
        previous: State the package is currently in.
        new: State being requested.

    Returns:
        (bool): True when the pair appears in `LEGAL_TRANSITIONS`.
    """
    return (previous, new) in LEGAL_TRANSITIONS


@dataclass(frozen=True)
class TransitionRecord:
    """One line of the transition log.

    The five fields are fixed by `02a` §-2.3 WP-BOOT-04 acceptance ⑧; adding a sixth would make
    the log's shape a second, undeclared truth.
    """

    wp: str
    previous_state: WorkPackageState
    new_state: WorkPackageState
    trigger: str
    evidence_hash: str

    def to_json(self) -> dict[str, str]:
        """Render the record as the five-key mapping persisted in the store.

        Returns:
            (dict[str, str]): Exactly five keys, states rendered as their string values.
        """
        return {
            "wp": self.wp,
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
            "trigger": self.trigger,
            "evidence_hash": self.evidence_hash,
        }

    @staticmethod
    def from_json(raw: dict[str, str]) -> TransitionRecord:
        """Rebuild a record from its persisted mapping.

        Args:
            raw: Mapping produced by `to_json`.

        Returns:
            (TransitionRecord): The reconstructed record.
        """
        return TransitionRecord(
            wp=raw["wp"],
            previous_state=WorkPackageState(raw["previous_state"]),
            new_state=WorkPackageState(raw["new_state"]),
            trigger=raw["trigger"],
            evidence_hash=raw["evidence_hash"],
        )
