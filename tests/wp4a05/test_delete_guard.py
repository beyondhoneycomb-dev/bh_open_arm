"""CG-4A-05e — a dataset delete with a referencing checkpoint warns (`FR-DAT-008`).

The guard reuses WP-3D-04's referencing query rather than re-deriving it: a dataset
that a recorded checkpoint trained on is not safe to delete, and the guard names the
checkpoint that would be orphaned.
"""

from __future__ import annotations

from backend.training.lineage import CheckpointId, TrainingLineageStore
from tests.wp4a05.support import fixture_record

_CONTENT_HASH = "content-hash-fixture"


def test_delete_of_referenced_dataset_is_not_safe_and_warns(tmp_path) -> None:
    """A recorded checkpoint makes its dataset unsafe to delete, with a warning."""
    checkpoint = CheckpointId("/runs/a", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), checkpoint, _CONTENT_HASH)
        guard = store.guard_delete(_CONTENT_HASH)
    assert not guard.safe
    warning = guard.warning()
    assert warning
    assert "/runs/a" in warning
    assert {(ref.output_dir, ref.step) for ref in guard.referencing} == {("/runs/a", 1000)}


def test_delete_of_unreferenced_dataset_is_safe(tmp_path) -> None:
    """A dataset no checkpoint trained on is safe to delete, with no warning."""
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), CheckpointId("/runs/a", 1000), _CONTENT_HASH)
        guard = store.guard_delete("some-other-dataset-hash")
    assert guard.safe
    assert guard.warning() == ""


def test_guard_reuses_the_wp3d04_referencing_query(tmp_path) -> None:
    """The referencing set matches WP-3D-04's own query on the same index file."""
    from backend.dataset.lineage import LineageStore

    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), CheckpointId("/runs/a", 1000), _CONTENT_HASH)
        store.record(fixture_record(episodes=(3, 4)), CheckpointId("/runs/b", 2000), _CONTENT_HASH)
        ours = {(ref.output_dir, ref.step) for ref in store.guard_delete(_CONTENT_HASH).referencing}
    with LineageStore(tmp_path / "index.sqlite") as reverse:
        theirs = {
            (ref.output_dir, ref.step) for ref in reverse.references_for_dataset(_CONTENT_HASH)
        }
    assert ours == theirs == {("/runs/a", 1000), ("/runs/b", 2000)}
