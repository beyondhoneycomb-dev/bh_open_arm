"""The verdict types the source-delete interlock produces (`02b` §7.2 WP-3C-06).

An episode is `PRESERVED` only when all four capture-preservation checks pass; one
failure makes it a `MISMATCH`. A delete is `DELETABLE` only when the converted
dataset is READY (WP-3D-05) *and* every episode is PRESERVED; anything else is
`REFUSED`, and a REFUSED decision deletes nothing. The distinction between a check
that ran and failed and a check that never ran is load-bearing: `deletable` tests
the required-check set rather than merely scanning for failures, so a decision that
silently skipped a check cannot certify a delete by omission — the exact failure
mode that would cause irreversible data loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.capture_interlock.constants import (
    REQUIRED_CAPTURE_CHECKS,
    VERDICT_DELETABLE,
    VERDICT_MISMATCH,
    VERDICT_PRESERVED,
    VERDICT_REFUSED,
)


class CaptureInterlockError(ValueError):
    """Raised when a delete is requested on a source the interlock has not certified.

    The delete path never removes a raw source without a `DELETABLE` decision; a
    caller that asks it to delete an uncertified source gets this exception rather
    than an executed deletion, which is the runtime twin of the `FAIL_BLOCKING`
    branch (`02b` §7.2 WP-3C-06: a delete with any check unmet is irreversible loss).
    """


class CheckStatus(Enum):
    """The binary outcome of one capture-preservation check — no warning level."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class PreservationCheck:
    """One capture-preservation check's outcome and the evidence behind it.

    Attributes:
        name: The check id (one of `constants.REQUIRED_CAPTURE_CHECKS`).
        status: PASS or FAIL.
        detail: A human-readable reason — the raw/converted values that disagree on
            FAIL, a short confirmation on PASS.
    """

    name: str
    status: CheckStatus
    detail: str

    @property
    def passed(self) -> bool:
        """Whether this check passed."""
        return self.status is CheckStatus.PASS


def passed(name: str, detail: str) -> PreservationCheck:
    """Build a passing capture-preservation result."""
    return PreservationCheck(name=name, status=CheckStatus.PASS, detail=detail)


def failed(name: str, detail: str) -> PreservationCheck:
    """Build a failing capture-preservation result."""
    return PreservationCheck(name=name, status=CheckStatus.FAIL, detail=detail)


@dataclass(frozen=True)
class EpisodePreservation:
    """The four checks' results for one episode, and its preservation verdict.

    Attributes:
        episode_index: The episode these results describe.
        results: One `PreservationCheck` per check that ran.
    """

    episode_index: int
    results: tuple[PreservationCheck, ...]

    def result(self, name: str) -> PreservationCheck | None:
        """Return the result for a named check, or None if it did not run."""
        for result in self.results:
            if result.name == name:
                return result
        return None

    @property
    def checks_ran(self) -> frozenset[str]:
        """The set of check names that produced a result for this episode."""
        return frozenset(result.name for result in self.results)

    @property
    def missing_checks(self) -> tuple[str, ...]:
        """Required checks that produced no result — an omission, not a pass."""
        ran = self.checks_ran
        return tuple(name for name in REQUIRED_CAPTURE_CHECKS if name not in ran)

    @property
    def failures(self) -> tuple[PreservationCheck, ...]:
        """Every check that ran and failed for this episode."""
        return tuple(result for result in self.results if not result.passed)

    @property
    def preserved(self) -> bool:
        """True only when all four required checks ran and every result passed.

        A missing check counts against preservation exactly as loudly as a failed
        one, so an episode whose checks were silently narrowed cannot be judged
        PRESERVED by omission.
        """
        return not self.missing_checks and not self.failures

    @property
    def verdict(self) -> str:
        """`PRESERVED` when `preserved`, else `MISMATCH`."""
        return VERDICT_PRESERVED if self.preserved else VERDICT_MISMATCH

    def reasons(self) -> tuple[str, ...]:
        """Human-readable reasons this episode is a MISMATCH, empty when PRESERVED."""
        out = [f"{result.name}: {result.detail}" for result in self.failures]
        out.extend(f"{name}: check did not run" for name in self.missing_checks)
        return tuple(out)


@dataclass(frozen=True)
class DeleteDecision:
    """Whether the raw source may be deleted, and the full evidence behind it.

    Attributes:
        raw_root: The raw capture source the decision is about.
        converted_root: The converted dataset the source was converted into.
        training_ready: Whether the converted dataset certified READY (WP-3D-05).
        ready_detail: Why READY did or did not hold (the WP-3D-05 reasons on FAIL).
        episodes: Per-episode preservation results, ascending by index.
    """

    raw_root: str
    converted_root: str
    training_ready: bool
    ready_detail: str
    episodes: tuple[EpisodePreservation, ...]

    @property
    def flagged_episodes(self) -> tuple[int, ...]:
        """The episodes that are a MISMATCH — preserved and flagged, never deleted."""
        return tuple(ep.episode_index for ep in self.episodes if not ep.preserved)

    @property
    def all_preserved(self) -> bool:
        """True when every episode is PRESERVED (all four checks passed for each)."""
        return bool(self.episodes) and all(ep.preserved for ep in self.episodes)

    @property
    def deletable(self) -> bool:
        """True only when the converted dataset is READY and every episode PRESERVED.

        Both conditions are required: the WP-3D-05 READY gate on the converted
        dataset, and the four capture-preservation checks on every episode. Either
        one unmet refuses the delete (`02b` §7.2 WP-3C-06).
        """
        return self.training_ready and self.all_preserved

    @property
    def verdict(self) -> str:
        """`DELETABLE` when `deletable`, else `REFUSED`."""
        return VERDICT_DELETABLE if self.deletable else VERDICT_REFUSED

    def refusal_reasons(self) -> tuple[str, ...]:
        """Why the delete is refused, empty when the decision is DELETABLE."""
        if self.deletable:
            return ()
        reasons: list[str] = []
        if not self.training_ready:
            reasons.append(f"converted dataset is not training-READY: {self.ready_detail}")
        if not self.episodes:
            reasons.append("no episodes were checked; nothing certifies the conversion")
        for episode in self.episodes:
            for reason in episode.reasons():
                reasons.append(f"episode {episode.episode_index} {reason}")
        return tuple(reasons)


@dataclass(frozen=True)
class DeleteOutcome:
    """The result of the delete path: the decision and whether the source was removed.

    Attributes:
        decision: The delete decision the outcome acted on.
        deleted: Whether the raw source was actually removed. True only for a
            `DELETABLE` decision; a `REFUSED` decision always leaves it in place.
        flagged_episodes: The episodes preserved and flagged on a REFUSED decision.
    """

    decision: DeleteDecision
    deleted: bool
    flagged_episodes: tuple[int, ...]
