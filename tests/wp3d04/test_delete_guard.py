"""WP-3D-04 ④: before a dataset delete, referencing checkpoints are queried + warned.

The store never deletes the dataset itself; it reports which checkpoints would be
orphaned so the caller can warn and refuse. These tests hold that a referenced
dataset is reported unsafe with a naming warning, and an unreferenced one is safe.
"""

from __future__ import annotations

from backend.dataset.lineage import LineageStore
from backend.dataset.lineage.constants import MEMORY_DATABASE
from tests.wp3d04._support import fixture_record


def test_a_referenced_dataset_is_unsafe_and_the_warning_names_the_checkpoints() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        content_hash = fixture_record((0,), "/x", 0).dataset_content_hash
        store.record(fixture_record((0, 1), "/runs/a", 1000, content_hash=content_hash))
        store.record(fixture_record((2, 3), "/runs/b", 2000, content_hash=content_hash))

        guard = store.guard_delete(content_hash)
        assert not guard.safe
        assert len(guard.referencing) == 2
        warning = guard.warning()
        assert "/runs/a@1000" in warning
        assert "/runs/b@2000" in warning


def test_an_unreferenced_dataset_is_safe_to_delete() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        store.record(fixture_record((0,), "/runs/a", 1000, content_hash="in-use"))
        guard = store.guard_delete("never-trained-on")
        assert guard.safe
        assert guard.referencing == ()
        assert guard.warning() == ""


def test_references_for_dataset_lists_every_referencing_checkpoint_once() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        content_hash = fixture_record((0,), "/x", 0).dataset_content_hash
        store.record(fixture_record((0, 1, 2), "/runs/a", 1000, content_hash=content_hash))
        store.record(fixture_record((0, 1, 2), "/runs/a", 2000, content_hash=content_hash))

        refs = store.references_for_dataset(content_hash)
        assert [(r.output_dir, r.step) for r in refs] == [("/runs/a", 1000), ("/runs/a", 2000)]
