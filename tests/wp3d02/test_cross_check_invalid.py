"""WP-3D-02 negative — a content mismatch makes the cross-check fire and the edit abort.

`02b` §8.2 WP-3D-02 ②③ and the FAIL_BLOCKING branch: one episode whose content does not
resolve to its expected original makes the whole output INVALID and aborts the operation;
a remap-less renumber is FAIL_BLOCKING because a label would attach to a different episode.
The pure cross-check is tested directly, and the engine's abort is driven by an operation
whose declared survivor order lies about which episode became which.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("lerobot")

from backend.dataset.edit import DeleteEpisodes, RemapMismatchError, commit_edit, resolve_remap
from backend.dataset.edit.constants import INVALID_MARKER_NAME
from backend.recorder.quality.label import Verdict
from backend.recorder.quality.store import DatasetStore
from tests.wp3d02.support import build_dataset, write_labels

_FRAME_COUNTS = (3, 4, 5, 6)
_VERDICTS = (Verdict.SUCCESS, Verdict.FAIL, Verdict.SUCCESS, Verdict.FAIL)


def test_resolve_remap_accepts_a_matching_renumber() -> None:
    """① A produced hash sequence equal to the survivors' resolves to a valid mapping."""
    original = {0: "a", 1: "b", 2: "c", 3: "d"}
    produced = {0: "a", 1: "c", 2: "d"}  # episode 1 deleted
    result = resolve_remap(original, produced, expected_survivors=[0, 2, 3])
    assert result.valid
    assert result.mapping == {0: 0, 1: 2, 2: 3}
    assert result.mismatches == ()


def test_resolve_remap_rejects_a_content_mismatch() -> None:
    """② One produced episode whose content does not match its expected original is INVALID."""
    original = {0: "a", 1: "b", 2: "c", 3: "d"}
    produced = {0: "a", 1: "b", 2: "d"}  # position 1 holds 'b', but survivor 2 hashes 'c'
    result = resolve_remap(original, produced, expected_survivors=[0, 2, 3])
    assert not result.valid
    assert any(m.produced_index == 1 for m in result.mismatches)


def test_resolve_remap_rejects_a_count_mismatch() -> None:
    """② A produced episode count that disagrees with the survivor list is INVALID."""
    original = {0: "a", 1: "b", 2: "c"}
    produced = {0: "a", 1: "c"}
    result = resolve_remap(original, produced, expected_survivors=[0, 1, 2])
    assert not result.valid
    assert result.mapping == {}


class _LyingDelete(DeleteEpisodes):
    """A delete whose declared survivor order is wrong — a remap that would mis-attach.

    The transformation is the real one (episode 1 deleted), but `expected_survivors`
    swaps the last two survivors, so the produced content no longer resolves to the
    declared original at those positions. It models a renumber whose sidecar mapping is
    wrong, which the 100% cross-check must catch.
    """

    def expected_survivors(self, dataset):  # noqa: ARG002 — deliberately ignores real content
        """Return a deliberately mis-ordered survivor list."""
        return {"output": [0, 3, 2]}


def test_engine_aborts_and_marks_invalid_on_mismatch(tmp_path: Path) -> None:
    """②③ A wrong remap aborts the edit, marks the output INVALID, and writes no sidecars."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, _FRAME_COUNTS)
    write_labels(root, _VERDICTS)
    output = tmp_path / "ds_edited"

    with pytest.raises(RemapMismatchError):
        commit_edit(root, stamped, _LyingDelete(episode_indices=(1,)), output)

    # The output is stamped INVALID and carries no remapped sidecars — the op aborted.
    assert (output / INVALID_MARKER_NAME).is_file()
    assert DatasetStore(output).episode_indices() == ()
    # Copy-on-write held: the original and its labels are untouched by the failed edit.
    assert set(DatasetStore(root).episode_indices()) == {0, 1, 2, 3}
