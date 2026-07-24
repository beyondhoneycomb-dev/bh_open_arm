"""WP-3C-07 ③: the user is presented a save/discard choice, with zero auto-save.

`02b` §7 WP-3C-07 ③: recovery presents a save/discard choice and auto-saves nothing —
its negative branch is FAIL_BLOCKING. These tests prove the runtime half: the presented
choice offers both options with no default, carries `auto_saved` False and
`requires_user_judgment` True, resolves nothing (phase-2 is deferred), and refuses to be
built for an episode that was somehow already accepted. The static half — no auto-save
call anywhere in the source — is `test_staticcheck.py`.
"""

from __future__ import annotations

import pytest

from backend.crash_recovery.choice import ChoiceOption, present_choice
from backend.recorder.quality.crash import RecoveryOutcome
from backend.recorder.quality.label import EpisodeLabel, EpisodeStatus, Verdict

_EPISODE = 3
_REASON = "crash-footerless-parquet"


def _pending_outcome() -> RecoveryOutcome:
    """A recovery outcome for a held, never-auto-saved crash episode."""
    return RecoveryOutcome(
        recovered=False,
        requires_user_judgment=True,
        auto_saved=False,
        salvaged_bytes=128,
        quarantine_path="/ds/meta/quarantine/episode_000003.parquet",
        reason=_REASON,
    )


def test_choice_offers_save_and_discard_with_no_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The presented choice offers both verdicts and picks neither by default."""
    label = EpisodeLabel.pending_judgment(_EPISODE, _REASON)

    choice = present_choice(_pending_outcome(), label)

    assert set(choice.options) == {ChoiceOption.SAVE, ChoiceOption.DISCARD}
    assert choice.resolved is None
    assert choice.requires_user_judgment is True


def test_presenting_a_choice_never_auto_saves() -> None:
    """The choice carries auto_saved False and leaves the label PENDING_JUDGMENT."""
    label = EpisodeLabel.pending_judgment(_EPISODE, _REASON)

    choice = present_choice(_pending_outcome(), label)

    assert choice.auto_saved is False
    # The label the drill holds is untouched by presenting the choice.
    assert label.status is EpisodeStatus.PENDING_JUDGMENT
    assert label.auto_saved is False
    assert label.requires_user_judgment() is True


def test_choice_refuses_an_already_accepted_episode() -> None:
    """A save/discard choice is never presented for accepted, auto-saved data."""
    accepted = EpisodeLabel.suggested(_EPISODE, Verdict.SUCCESS)
    assert accepted.auto_saved is True

    with pytest.raises(ValueError, match="already-accepted"):
        present_choice(_pending_outcome(), accepted)


def test_choice_payload_carries_the_honest_recovery_facts() -> None:
    """The presentation payload surfaces the recovery facts a human weighs, unresolved."""
    label = EpisodeLabel.pending_judgment(_EPISODE, _REASON)

    payload = present_choice(_pending_outcome(), label).to_dict()

    assert payload["options"] == [ChoiceOption.SAVE.value, ChoiceOption.DISCARD.value]
    assert payload["auto_saved"] is False
    assert payload["resolved"] is None
    assert payload["recovered"] is False
    assert payload["salvaged_bytes"] == 128
    assert payload["reason"] == _REASON
