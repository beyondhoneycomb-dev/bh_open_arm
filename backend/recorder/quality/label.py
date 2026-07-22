"""Episode judgment and label — the per-episode attribute the store persists (WP-3B-12, `02b` §5.2).

`02b` §5.2 WP-3B-12 makes success/fail an episode attribute carried by a sidecar, not
a re-recording of the parquet/mp4 (①). Two independent judgments coexist: an automatic
SUGGESTION and a human verdict — both preserved, the human's taking priority, and a
mismatch between them left queryable (②). The one hard rule the negative branch fixes
("자동 폐기가 사유 없이 발동 → FAIL_BLOCKING"): a discard or abort must always carry a
reason, so an `EpisodeLabel` cannot enter the ABORTED or PENDING state with an empty one.

A soft-stopped episode (disk-low) and a crash-recovered episode are never auto-saved:
each is routed to human judgment with `auto_saved` False, so nothing reaches the store
as accepted data without a person deciding (④⑤).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class QualityLabelError(ValueError):
    """An episode label violates a WP-3B-12 invariant.

    Raised when an abort or pending-judgment label omits its reason, or when the
    `auto_saved` flag contradicts a status that forbids auto-saving.
    """


class Verdict(StrEnum):
    """The outcome a judge assigns an episode."""

    SUCCESS = "success"
    FAIL = "fail"


class Provenance(StrEnum):
    """Who rendered a judgment.

    `AUTO` is the offline auto-judge's suggestion; `MANUAL` is a human verdict that
    overrides it. Both are retained on the label so the disagreement stays visible.
    """

    AUTO = "auto"
    MANUAL = "manual"


class EpisodeStatus(StrEnum):
    """The lifecycle state of an episode's label.

    `JUDGED` — a verdict has been rendered and the episode's data may be kept.
    `PENDING_JUDGMENT` — awaiting a human decision (crash recovery), never auto-saved.
    `ABORTED` — soft-stopped mid-episode (disk-low), not accepted data, never auto-saved.
    """

    JUDGED = "judged"
    PENDING_JUDGMENT = "pending_judgment"
    ABORTED = "aborted"


class AbortReason(StrEnum):
    """The canonical reasons an episode is aborted or held for judgment.

    A reason is mandatory: an unexplained discard is the WP-3B-12 FAIL_BLOCKING defect.
    """

    DISK_LOW = "disk-low"
    CRASH_FOOTERLESS_PARQUET = "crash-footerless-parquet"


@dataclass(frozen=True)
class Judgment:
    """One judgment of an episode: a verdict and who rendered it."""

    verdict: Verdict
    provenance: Provenance

    def to_dict(self) -> dict[str, str]:
        """Serialise to a JSON-safe mapping."""
        return {"verdict": self.verdict.value, "provenance": self.provenance.value}

    @classmethod
    def from_dict(cls, body: dict[str, Any]) -> Judgment:
        """Reconstruct a judgment from its serialised form."""
        return cls(verdict=Verdict(body["verdict"]), provenance=Provenance(body["provenance"]))


@dataclass(frozen=True)
class EpisodeLabel:
    """The label an episode carries: automatic suggestion, human verdict, and status.

    Both `auto` and `manual` are kept whenever present, so a suggestion is never lost
    when a human overrides it and a mismatch stays queryable (`is_conflicting`). The
    frozen shape makes every transition an explicit new instance rather than a mutation.

    Attributes:
        episode_index: The episode this label annotates, the sidecar join key.
        status: The lifecycle state.
        auto: The offline auto-judge's suggestion, or None.
        manual: The human verdict, or None; overrides `auto` when present.
        abort_reason: Why the episode was aborted or held for judgment; required for
            ABORTED and PENDING_JUDGMENT, absent for JUDGED.
        auto_saved: Whether the store may persist this episode as accepted data without
            a human sign-off. Always False for ABORTED and PENDING_JUDGMENT.
    """

    episode_index: int
    status: EpisodeStatus
    auto: Judgment | None
    manual: Judgment | None
    abort_reason: str | None
    auto_saved: bool

    def __post_init__(self) -> None:
        """Enforce the reason-mandatory and no-auto-save invariants."""
        if self.status in (EpisodeStatus.ABORTED, EpisodeStatus.PENDING_JUDGMENT):
            if not self.abort_reason:
                raise QualityLabelError(
                    f"episode {self.episode_index} in status {self.status.value} needs a reason; "
                    "an unexplained discard is the WP-3B-12 FAIL_BLOCKING defect"
                )
            if self.auto_saved:
                raise QualityLabelError(
                    f"episode {self.episode_index} in status {self.status.value} must not be "
                    "auto-saved; it is routed to human judgment"
                )
        if self.status is EpisodeStatus.JUDGED and self.auto is None and self.manual is None:
            raise QualityLabelError(
                f"episode {self.episode_index} is JUDGED but carries no verdict"
            )

    @classmethod
    def judged(
        cls,
        episode_index: int,
        auto: Judgment | None = None,
        manual: Judgment | None = None,
    ) -> EpisodeLabel:
        """A judged episode whose data is kept and labelled.

        Args:
            episode_index: The episode index.
            auto: The auto-judge suggestion, if any.
            manual: The human verdict, if any. At least one of the two is required.

        Returns:
            (EpisodeLabel) A JUDGED, auto-saved label.
        """
        return cls(
            episode_index=episode_index,
            status=EpisodeStatus.JUDGED,
            auto=auto,
            manual=manual,
            abort_reason=None,
            auto_saved=True,
        )

    @classmethod
    def suggested(cls, episode_index: int, verdict: Verdict) -> EpisodeLabel:
        """A judged episode carrying only the automatic suggestion (no human verdict yet)."""
        return cls.judged(episode_index, auto=Judgment(verdict, Provenance.AUTO))

    @classmethod
    def aborted(cls, episode_index: int, reason: str) -> EpisodeLabel:
        """A soft-stopped episode: not accepted data, reason attached, never auto-saved.

        Args:
            episode_index: The episode index.
            reason: Why it was aborted; must be non-empty.

        Returns:
            (EpisodeLabel) An ABORTED label with `auto_saved` False.
        """
        return cls(
            episode_index=episode_index,
            status=EpisodeStatus.ABORTED,
            auto=None,
            manual=None,
            abort_reason=reason,
            auto_saved=False,
        )

    @classmethod
    def pending_judgment(cls, episode_index: int, reason: str) -> EpisodeLabel:
        """A crash-recovered episode held for a human decision; never auto-saved.

        Args:
            episode_index: The episode index.
            reason: Why judgment is required; must be non-empty.

        Returns:
            (EpisodeLabel) A PENDING_JUDGMENT label with `auto_saved` False.
        """
        return cls(
            episode_index=episode_index,
            status=EpisodeStatus.PENDING_JUDGMENT,
            auto=None,
            manual=None,
            abort_reason=reason,
            auto_saved=False,
        )

    def with_auto(self, verdict: Verdict) -> EpisodeLabel:
        """Attach an automatic suggestion, preserving any existing human verdict."""
        return EpisodeLabel.judged(
            self.episode_index, auto=Judgment(verdict, Provenance.AUTO), manual=self.manual
        )

    def with_manual(self, verdict: Verdict) -> EpisodeLabel:
        """Attach a human verdict, preserving any existing suggestion.

        The human verdict takes priority for `effective_verdict`, but the suggestion is
        retained so a later query can compare the two (`is_conflicting`). Resolving a
        PENDING_JUDGMENT episode this way accepts it as JUDGED, auto-saved data.
        """
        return EpisodeLabel.judged(
            self.episode_index, auto=self.auto, manual=Judgment(verdict, Provenance.MANUAL)
        )

    def discard(self, reason: str) -> EpisodeLabel:
        """Resolve this label to a reasoned discard — the human's decision to drop it."""
        return EpisodeLabel.aborted(self.episode_index, reason)

    def effective_verdict(self) -> Verdict | None:
        """The verdict that governs: the human's when present, else the suggestion."""
        if self.manual is not None:
            return self.manual.verdict
        if self.auto is not None:
            return self.auto.verdict
        return None

    def is_conflicting(self) -> bool:
        """Whether the automatic suggestion and the human verdict disagree."""
        return (
            self.auto is not None
            and self.manual is not None
            and self.auto.verdict != self.manual.verdict
        )

    def requires_user_judgment(self) -> bool:
        """Whether a human must still decide before this episode can be accepted."""
        return self.status is EpisodeStatus.PENDING_JUDGMENT and self.manual is None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe mapping for the on-disk sidecar."""
        return {
            "episode_index": self.episode_index,
            "status": self.status.value,
            "auto": self.auto.to_dict() if self.auto is not None else None,
            "manual": self.manual.to_dict() if self.manual is not None else None,
            "abort_reason": self.abort_reason,
            "auto_saved": self.auto_saved,
        }

    @classmethod
    def from_dict(cls, body: dict[str, Any]) -> EpisodeLabel:
        """Reconstruct a label from its serialised form."""
        auto = body.get("auto")
        manual = body.get("manual")
        return cls(
            episode_index=body["episode_index"],
            status=EpisodeStatus(body["status"]),
            auto=Judgment.from_dict(auto) if auto is not None else None,
            manual=Judgment.from_dict(manual) if manual is not None else None,
            abort_reason=body.get("abort_reason"),
            auto_saved=body["auto_saved"],
        )
