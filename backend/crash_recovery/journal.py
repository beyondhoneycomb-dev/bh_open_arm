"""The session journal and journal-based resume (WP-3C-07 ④/⑤).

`02b` §7 WP-3C-07 ④/⑤: a crash must be resumable. The recorder stamps each session's
`repo_id` once, at creation, and that stamped name is the one carried through display,
storage and every later reference (WP-3B-11 ⑤). A resume therefore must NOT create a
new dataset — that would call `stamp_repo_id()` a second time and mint a *different*
name, orphaning the crashed session's data. Instead the journal records the already
stamped id, the task, the episode counter and the config while recording, so a resume
reopens the existing dataset under the existing name.

The one hard rule this module exists to hold: `restore_session` returns the stamped id
**verbatim** and never stamps. `has_double_stamp` is the runtime tripwire — a resumed
id carrying two trailing stamp groups is proof `stamp_repo_id()` ran again, which
WP-3C-07 ⑤ forbids.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from backend.crash_recovery.constants import (
    JOURNAL_ENCODING,
    JOURNAL_RELATIVE_PATH,
    REPO_ID_STAMP_REGEX,
)

# Two consecutive stamp groups at the tail — `..._20260724_234900_20260725_010203` —
# is the signature of a `repo_id` that was stamped, then stamped again on resume.
_DOUBLE_STAMP = re.compile(rf"(?:{REPO_ID_STAMP_REGEX[:-1]}){{2}}$")


@dataclass(frozen=True)
class SessionJournal:
    """A crash-surviving record of a recording session's resumable state.

    Written beside the dataset while recording (checkpointed after each saved
    episode) so a resume restores the session without re-deriving anything. The
    stamped id is stored, never re-computed, because re-computing it is exactly the
    WP-3C-07 ⑤ defect.

    Attributes:
        schema_version: The journal format version.
        stamped_repo_id: The id the recorder stamped at creation — the existing name a
            resume must reuse unchanged.
        single_task: The task label the session records under.
        saved_episodes: How many episodes were saved before the crash; also the index
            the next episode takes, so a resume continues without re-numbering.
        fps: The recording frame rate.
        bimanual: Whether the session records two arms.
        use_velocity_and_torque: Whether `observation.state` carries `.vel`/`.torque`.
        num_episodes: The episode target the session was aiming for.
        episode_steps: The per-episode frame budget.
        reset_steps: The unrecorded environment-reset frame budget.
    """

    schema_version: int
    stamped_repo_id: str
    single_task: str
    saved_episodes: int
    fps: int
    bimanual: bool
    use_velocity_and_torque: bool
    num_episodes: int
    episode_steps: int
    reset_steps: int

    def to_dict(self) -> dict[str, object]:
        """Serialise to a JSON-safe mapping."""
        return {
            "schema_version": self.schema_version,
            "stamped_repo_id": self.stamped_repo_id,
            "single_task": self.single_task,
            "saved_episodes": self.saved_episodes,
            "fps": self.fps,
            "bimanual": self.bimanual,
            "use_velocity_and_torque": self.use_velocity_and_torque,
            "num_episodes": self.num_episodes,
            "episode_steps": self.episode_steps,
            "reset_steps": self.reset_steps,
        }

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> SessionJournal:
        """Reconstruct a journal from its serialised form."""
        return cls(
            schema_version=int(body["schema_version"]),  # type: ignore[arg-type]
            stamped_repo_id=str(body["stamped_repo_id"]),
            single_task=str(body["single_task"]),
            saved_episodes=int(body["saved_episodes"]),  # type: ignore[arg-type]
            fps=int(body["fps"]),  # type: ignore[arg-type]
            bimanual=bool(body["bimanual"]),
            use_velocity_and_torque=bool(body["use_velocity_and_torque"]),
            num_episodes=int(body["num_episodes"]),  # type: ignore[arg-type]
            episode_steps=int(body["episode_steps"]),  # type: ignore[arg-type]
            reset_steps=int(body["reset_steps"]),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class ResumePlan:
    """What a resume needs to reopen a crashed session — with the existing name.

    The whole point of the type is `stamped_repo_id`: it is the journal's stamped id
    copied through unchanged. A caller reopens the existing dataset with this id; it
    must never route through the recorder's create/stamp path, which would mint a new
    name (WP-3C-07 ⑤).

    Attributes:
        stamped_repo_id: The existing stamped id, verbatim from the journal.
        single_task: The task label to continue recording under.
        next_episode_index: The index the next saved episode takes (the crash-time
            episode counter); already-saved episodes are not re-recorded.
        remaining_episodes: How many episodes are left to reach the session target.
        fps: The recording frame rate.
        bimanual: Whether the session records two arms.
        use_velocity_and_torque: Whether `observation.state` carries `.vel`/`.torque`.
        root: The dataset root to reopen.
    """

    stamped_repo_id: str
    single_task: str
    next_episode_index: int
    remaining_episodes: int
    fps: int
    bimanual: bool
    use_velocity_and_torque: bool
    root: Path


def journal_path(root: Path) -> Path:
    """The session-journal path for a dataset root."""
    return root / JOURNAL_RELATIVE_PATH


def write_journal(root: Path, journal: SessionJournal) -> Path:
    """Write the session journal beside the dataset, creating `meta/` if needed.

    Args:
        root: The dataset root.
        journal: The state to persist.

    Returns:
        (Path) The journal path written.
    """
    path = journal_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(journal.to_dict(), ensure_ascii=False, indent=2), encoding=JOURNAL_ENCODING
    )
    return path


def read_journal(root: Path) -> SessionJournal:
    """Read the session journal for a dataset root.

    Args:
        root: The dataset root.

    Returns:
        (SessionJournal) The persisted state.

    Raises:
        FileNotFoundError: When no journal exists — the session cannot be resumed.
    """
    path = journal_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"no session journal at {path}; the session cannot be resumed")
    return SessionJournal.from_dict(json.loads(path.read_text(encoding=JOURNAL_ENCODING)))


def restore_session(root: Path) -> ResumePlan:
    """Build a resume plan from the journal, carrying the stamped id through unchanged.

    This is the WP-3C-07 ⑤ guarantee in code: the returned `stamped_repo_id` is the
    journal's id *verbatim*. Nothing here calls `stamp_repo_id()` — a resume reuses the
    existing name, never a freshly minted one.

    Args:
        root: The dataset root holding the journal.

    Returns:
        (ResumePlan) The plan to reopen the existing dataset under its existing name.
    """
    journal = read_journal(root)
    remaining = max(journal.num_episodes - journal.saved_episodes, 0)
    return ResumePlan(
        stamped_repo_id=journal.stamped_repo_id,
        single_task=journal.single_task,
        next_episode_index=journal.saved_episodes,
        remaining_episodes=remaining,
        fps=journal.fps,
        bimanual=journal.bimanual,
        use_velocity_and_torque=journal.use_velocity_and_torque,
        root=root,
    )


def has_double_stamp(repo_id: str) -> bool:
    """Whether a `repo_id` carries two trailing stamp groups — a re-stamp divergence.

    A single `stamp_repo_id()` yields one `_YYYYMMDD_HHMMSS` tail. Two tails mean the
    id was stamped twice, which is the exact name divergence WP-3C-07 ⑤ forbids on
    resume. The runtime resume asserts this is False on the id it carries forward.

    Args:
        repo_id: The id to inspect.

    Returns:
        (bool) True when a doubled stamp is present.
    """
    return _DOUBLE_STAMP.search(repo_id) is not None
