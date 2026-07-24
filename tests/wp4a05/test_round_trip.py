"""CG-4A-05c — the bidirectional query round-trips: episodes_of(checkpoints_of(E)) ⊇ E.

The query composes WP-3D-04's reverse index, so this proves both directions agree:
every episode in E is attributed to at least one checkpoint, and every such
checkpoint's episode set contains it back.
"""

from __future__ import annotations

from backend.training.lineage import (
    CheckpointId,
    EpisodeRef,
    TrainingLineageStore,
)
from tests.wp4a05.support import fixture_record

_CONTENT_HASH = "content-hash-fixture"


def _episode_set(indices: tuple[int, ...]) -> set[EpisodeRef]:
    """Build the `EpisodeRef` set for the fixture dataset."""
    return {EpisodeRef(_CONTENT_HASH, index) for index in indices}


def _round_trip(store: TrainingLineageStore, episodes: set[EpisodeRef]) -> set[EpisodeRef]:
    """Compute episodes_of(checkpoints_of(E)) for the given episode set."""
    got: set[EpisodeRef] = set()
    for ref in store.checkpoints_of(episodes):
        got.update(store.episodes_of(CheckpointId(ref.output_dir, ref.step)))
    return got


def test_round_trip_superset_single_checkpoint(tmp_path) -> None:
    """One checkpoint on episodes {0,1,2}: the round-trip returns a superset of E."""
    with TrainingLineageStore(tmp_path) as store:
        store.record(
            fixture_record(episodes=(0, 1, 2)), CheckpointId("/runs/a", 1000), _CONTENT_HASH
        )
        for probe in ((0,), (1, 2), (0, 1, 2)):
            requested = _episode_set(probe)
            assert requested <= _round_trip(store, requested)


def test_round_trip_superset_overlapping_checkpoints(tmp_path) -> None:
    """Two checkpoints on overlapping sets: the union comes back on the round-trip."""
    with TrainingLineageStore(tmp_path) as store:
        store.record(
            fixture_record(episodes=(0, 1, 2)), CheckpointId("/runs/a", 1000), _CONTENT_HASH
        )
        store.record(
            fixture_record(episodes=(2, 3, 4)), CheckpointId("/runs/b", 1000), _CONTENT_HASH
        )
        # Probing episode 2 reaches both checkpoints, so their whole union returns.
        got = _round_trip(store, _episode_set((2,)))
        assert _episode_set((0, 1, 2, 3, 4)) <= got


def test_checkpoints_of_deduplicates_across_the_episode_set(tmp_path) -> None:
    """A checkpoint referenced by several probed episodes appears exactly once."""
    with TrainingLineageStore(tmp_path) as store:
        store.record(
            fixture_record(episodes=(0, 1, 2)), CheckpointId("/runs/a", 1000), _CONTENT_HASH
        )
        refs = store.checkpoints_of(_episode_set((0, 1, 2)))
        identities = [(ref.output_dir, ref.step) for ref in refs]
        assert identities == [("/runs/a", 1000)]


def test_query_uses_the_wp3d04_index_file(tmp_path) -> None:
    """The bidirectional query is backed by WP-3D-04's `index.sqlite`, not a fork."""
    from backend.dataset.lineage import LineageStore

    with TrainingLineageStore(tmp_path) as store:
        store.record(
            fixture_record(episodes=(0, 1, 2)), CheckpointId("/runs/a", 1000), _CONTENT_HASH
        )
    # The same file opens as a WP-3D-04 store and answers the reverse query directly.
    with LineageStore(tmp_path / "index.sqlite") as reverse:
        refs = reverse.checkpoints_for_episode(_CONTENT_HASH, 1)
    assert [(ref.output_dir, ref.step) for ref in refs] == [("/runs/a", 1000)]
