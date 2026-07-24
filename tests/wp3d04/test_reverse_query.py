"""WP-3D-04 ①: the "checkpoints that used this episode" reverse query works.

LeRobot restores lineage forward only; this is the direction it never keeps, so
these tests are the proof the store answers it: an episode maps back to exactly the
checkpoints that trained on it, across runs that used overlapping episode slices,
and never across a different dataset.
"""

from __future__ import annotations

from backend.dataset.lineage import LineageStore
from backend.dataset.lineage.constants import MEMORY_DATABASE
from tests.wp3d04._support import fixture_record


def test_episode_maps_back_to_every_checkpoint_that_used_it() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        content_hash = fixture_record(episodes=(0,), output_dir="/x", step=0).dataset_content_hash
        store.record(fixture_record((0, 1, 2), "/runs/a", 1000, content_hash=content_hash))
        store.record(fixture_record((2, 3), "/runs/b", 2000, content_hash=content_hash))

        shared = store.checkpoints_for_episode(content_hash, 2)
        assert [(ref.output_dir, ref.step) for ref in shared] == [
            ("/runs/a", 1000),
            ("/runs/b", 2000),
        ]

        only_a = store.checkpoints_for_episode(content_hash, 0)
        assert [ref.output_dir for ref in only_a] == ["/runs/a"]

        only_b = store.checkpoints_for_episode(content_hash, 3)
        assert [ref.output_dir for ref in only_b] == ["/runs/b"]


def test_reverse_query_is_empty_for_an_unused_episode() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        record = fixture_record((0, 1), "/runs/a", 1000)
        store.record(record)
        assert store.checkpoints_for_episode(record.dataset_content_hash, 9) == ()


def test_reverse_query_does_not_cross_datasets() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        store.record(fixture_record((0, 1), "/runs/a", 1000, content_hash="dataset-A"))
        store.record(fixture_record((0, 1), "/runs/b", 1000, content_hash="dataset-B"))

        a_hits = store.checkpoints_for_episode("dataset-A", 0)
        assert [ref.output_dir for ref in a_hits] == ["/runs/a"]
        assert all(ref.dataset_content_hash == "dataset-A" for ref in a_hits)


def test_reverse_query_returns_the_full_checkpoint_identity() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        record = fixture_record(
            (5,), "/runs/only", 4200, stats_hash="stats-abcd", revision="rev-99"
        )
        store.record(record)

        (ref,) = store.checkpoints_for_episode(record.dataset_content_hash, 5)
        assert ref.step == 4200
        assert ref.stats_hash == "stats-abcd"
        assert ref.revision == "rev-99"
        assert ref.repo_id == record.repo_id
