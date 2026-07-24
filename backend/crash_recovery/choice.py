"""The save/discard choice presented after recovery (WP-3C-07 ③, NO AUTO-SAVE).

`02b` §7 WP-3C-07 ③: after a crash is recovered, the user is presented a save/discard
choice, and the auto-save count is zero — a partial episode is unlabelled and its task
incomplete, so accepting it as data is a decision only a human may make. The negative
branch is FAIL_BLOCKING: any automatic save is a defect.

This module builds the *presentation* of that choice and nothing more. Phase-1 is
`AI-offline`; phase-2 — the human's save/discard verdict — is `Human-judgment` and
deferred (`02b` §7 WP-3C-07). So `present_choice` renders the options and the honest
recovery facts a person needs, and stops. It never resolves the choice: there is no
call here to `save_episode`, to `EpisodeLabel.with_manual`, or to anything that would
mark the episode accepted. The recovered episode stays PENDING_JUDGMENT, `auto_saved`
False, exactly as the recorder band's `recover` left it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.recorder.quality.crash import RecoveryOutcome
from backend.recorder.quality.label import EpisodeLabel, EpisodeStatus


class ChoiceOption(StrEnum):
    """The two verdicts a human may render on a recovered episode (phase-2)."""

    SAVE = "save"
    DISCARD = "discard"


@dataclass(frozen=True)
class RecoveryChoice:
    """The save/discard choice a recovered episode is presented for human judgment.

    Every field is a fact the presentation shows or a guard the presentation asserts;
    none of it decides. `resolved` is always None here — phase-1 presents, phase-2
    (deferred) resolves — and `auto_saved` is always False, which is the WP-3C-07 ③
    invariant made a value a caller can check.

    Attributes:
        episode_index: The recovered episode awaiting a verdict.
        options: The verdicts offered — save or discard, no default among them, because
            a default would be an automatic decision.
        recovered: Whether any table read back from the crash artefact (honest, from the
            recovery attempt); a person weighs this, it does not decide for them.
        salvaged_bytes: The bytes that physically survived the crash.
        quarantine_path: Where the crash artefact was isolated to.
        reason: Why the episode is held for judgment.
        requires_user_judgment: Always True — a crash artefact is never accepted without
            a person deciding.
        auto_saved: Always False — presenting a choice performs no save.
        resolved: Always None in phase-1; the human verdict path is deferred.
    """

    episode_index: int
    options: tuple[ChoiceOption, ...]
    recovered: bool
    salvaged_bytes: int
    quarantine_path: str
    reason: str
    requires_user_judgment: bool
    auto_saved: bool
    resolved: ChoiceOption | None

    def to_dict(self) -> dict[str, object]:
        """Render the choice as the presentation payload a GUI/WS layer displays."""
        return {
            "episode_index": self.episode_index,
            "options": [option.value for option in self.options],
            "recovered": self.recovered,
            "salvaged_bytes": self.salvaged_bytes,
            "quarantine_path": self.quarantine_path,
            "reason": self.reason,
            "requires_user_judgment": self.requires_user_judgment,
            "auto_saved": self.auto_saved,
            "resolved": self.resolved.value if self.resolved is not None else None,
        }


def present_choice(outcome: RecoveryOutcome, label: EpisodeLabel) -> RecoveryChoice:
    """Build the save/discard presentation from a recovery outcome and its label.

    The label must be PENDING_JUDGMENT and not auto-saved — the state the recorder
    band's `recover` produces — because presenting a choice for an episode that was
    somehow already accepted would defeat the no-auto-save rule. The presentation offers
    both options with no default and resolves nothing.

    Args:
        outcome: The honest recovery outcome (isolation, salvaged bytes, recovered flag).
        label: The episode's pending-judgment label.

    Returns:
        (RecoveryChoice) The unresolved save/discard presentation.

    Raises:
        ValueError: When the label is not a not-yet-accepted, non-auto-saved pending
            episode — the only state a save/discard choice may be presented for.
    """
    if label.status is not EpisodeStatus.PENDING_JUDGMENT or label.auto_saved:
        raise ValueError(
            f"episode {label.episode_index} is not an unaccepted pending episode "
            f"(status={label.status.value}, auto_saved={label.auto_saved}); "
            "a save/discard choice must never be presented for already-accepted data"
        )
    return RecoveryChoice(
        episode_index=label.episode_index,
        options=(ChoiceOption.SAVE, ChoiceOption.DISCARD),
        recovered=outcome.recovered,
        salvaged_bytes=outcome.salvaged_bytes,
        quarantine_path=outcome.quarantine_path,
        reason=outcome.reason,
        requires_user_judgment=True,
        auto_saved=False,
        resolved=None,
    )
