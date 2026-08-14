"""A checkpoint directory that exists is not a checkpoint that can be read.

The writer creates `checkpoints/<step>/` and fills `training_state/training_step.json` at two
different instants, and anything watching a run reads between them as a matter of course — a
training job saves while the orchestrator, the dashboard and a resume all look on. Treating the
directory's existence as the checkpoint's completeness makes the reader open a file the writer
has not created, and the failure lands as a `FileNotFoundError` out of `find_last` rather than as
"no checkpoint yet".

The window is built directly here rather than reproduced under load. Under `-n auto` the same
defect surfaced once in a run and not at all in the two after it, which is a test that reports the
machine's mood; the directories below are laid out by hand, so the case is the same one every
time and the assertion is about `find_last` rather than about scheduling.
"""

from __future__ import annotations

import json

from backend.training.orchestrator.checkpoints import (
    LAST_CHECKPOINT_LINK,
    TRAINING_STATE_DIR,
    TRAINING_STEP_FILE,
    checkpoints_root,
    find_last,
    is_complete,
)

# Two steps, so "the newest complete one" can differ from "the newest one".
EARLIER_STEP = 1
LATER_STEP = 2


def _write_complete(root, step: int):
    """Create a checkpoint directory with its training-state file, as a finished save looks."""
    directory = root / f"{step:06d}"
    state = directory / TRAINING_STATE_DIR
    state.mkdir(parents=True)
    (state / TRAINING_STEP_FILE).write_text(json.dumps({"step": step}), encoding="utf-8")
    return directory


def _write_half(root, step: int):
    """Create the directory a save has started but not filled: no training-state file."""
    directory = root / f"{step:06d}"
    (directory / TRAINING_STATE_DIR).mkdir(parents=True)
    return directory


def test_a_directory_without_its_state_file_is_not_complete(tmp_path) -> None:
    """The distinction the whole fix rests on, stated on its own."""
    root = checkpoints_root(tmp_path)
    root.mkdir(parents=True)

    assert not is_complete(_write_half(root, EARLIER_STEP))
    assert is_complete(_write_complete(root, LATER_STEP))


def test_a_half_written_checkpoint_is_not_returned(tmp_path) -> None:
    """With nothing finished, the answer is "none" rather than an unreadable path.

    Returning it and raising on the read is the failure this replaces: the caller asked which
    checkpoint it could resume from, and a directory with no state file is not an answer.
    """
    root = checkpoints_root(tmp_path)
    root.mkdir(parents=True)
    _write_half(root, EARLIER_STEP)

    assert find_last(tmp_path) is None


def test_the_newest_complete_checkpoint_wins_over_a_newer_half_written_one(tmp_path) -> None:
    """The ordinary state of a running job: step N saved, step N+1 being written.

    Taking the highest number would pick the one currently being filled — which is exactly the
    moment a resume is most likely to be asked for, because something just interrupted the run.
    """
    root = checkpoints_root(tmp_path)
    root.mkdir(parents=True)
    _write_complete(root, EARLIER_STEP)
    _write_half(root, LATER_STEP)

    found = find_last(tmp_path)

    assert found is not None
    assert found.step == EARLIER_STEP


def test_a_complete_checkpoint_is_still_found(tmp_path) -> None:
    """The rule is not a blanket refusal, or no run could ever resume."""
    root = checkpoints_root(tmp_path)
    root.mkdir(parents=True)
    _write_complete(root, EARLIER_STEP)
    _write_complete(root, LATER_STEP)

    found = find_last(tmp_path)

    assert found is not None
    assert found.step == LATER_STEP


def test_a_link_onto_a_half_written_checkpoint_falls_back(tmp_path) -> None:
    """The link is repointed atomically; what it points at is not complete until the writer says.

    A link already moved onto the directory being filled resolves fine and reads nothing, so the
    completeness check has to cover the preferred path too — otherwise the fallback only helps a
    tree that has no link at all, which is not the case that bites.
    """
    root = checkpoints_root(tmp_path)
    root.mkdir(parents=True)
    _write_complete(root, EARLIER_STEP)
    half = _write_half(root, LATER_STEP)
    (root / LAST_CHECKPOINT_LINK).symlink_to(half, target_is_directory=True)

    found = find_last(tmp_path)

    assert found is not None
    assert found.step == EARLIER_STEP


def test_a_link_onto_a_complete_checkpoint_is_used(tmp_path) -> None:
    """The preferred path still wins when what it points at is readable."""
    root = checkpoints_root(tmp_path)
    root.mkdir(parents=True)
    _write_complete(root, EARLIER_STEP)
    complete = _write_complete(root, LATER_STEP)
    (root / LAST_CHECKPOINT_LINK).symlink_to(complete, target_is_directory=True)

    found = find_last(tmp_path)

    assert found is not None
    assert found.step == LATER_STEP


def test_an_empty_checkpoints_root_is_none(tmp_path) -> None:
    """A run that has saved nothing reports nothing, not an error."""
    checkpoints_root(tmp_path).mkdir(parents=True)

    assert find_last(tmp_path) is None
