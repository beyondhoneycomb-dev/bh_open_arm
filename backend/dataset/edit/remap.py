"""Sidecar remap under a renumber, verified by the 100% content cross-check (WP-3D-02).

This is the module the FAIL_BLOCKING rule rests on: "재매핑 없이 실행 → FAIL_BLOCKING
(라벨이 다른 에피소드에 들러붙는다)" (`02b` §8.2 WP-3D-02). When a renumber rewrites
episode indices, the per-episode quality sidecar (WP-3B-12's `meta/quality/episode_*.json`)
must follow the *content* it labels, not the index it used to sit at.

`resolve_remap` is the cross-check. It reverse-looks-up every produced episode's content
hash in the original, and confirms — for every episode, no sampling — that produced
episode *j* carries the content of the original episode the operation says survives at
position *j*. Any episode whose content does not resolve to its expected original is a
mismatch, and one mismatch makes the whole remap `INVALID` (`02b` §8.2 ①②). `apply_remap`
then carries each surviving episode's sidecar to its new index, preserving the report body
verbatim, and re-reads the result to prove the written indices are exactly the mapping.

The quality-store layout is consumed from WP-3B-12 (`DatasetStore`), not re-derived: the
sidecar path convention has one owner.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.dataset.edit.constants import EPISODE_INDEX_COLUMN
from backend.recorder.quality.store import DatasetStore

# The nested key inside a sidecar JSON that repeats the episode index on the label.
# Consumed from WP-3B-12's `EpisodeLabel.to_dict()` shape; patched in lockstep with the
# top-level index so a remapped sidecar is internally consistent.
_LABEL_KEY = "label"
_EPISODE_INDEX_FIELD = EPISODE_INDEX_COLUMN


@dataclass(frozen=True)
class Mismatch:
    """One produced episode whose content did not resolve to its expected original.

    Attributes:
        produced_index: The new episode index that failed the cross-check.
        expected_original_index: The original index the operation said should be here.
        produced_hash: The content hash actually found at the produced index.
        expected_hash: The content hash of the expected original, or None when that
            original index does not exist.
    """

    produced_index: int
    expected_original_index: int
    produced_hash: str
    expected_hash: str | None


@dataclass(frozen=True)
class RemapResult:
    """The outcome of the content cross-check for one output dataset.

    Attributes:
        mapping: Produced (new) episode index to original (old) episode index, for
            every produced episode, when the cross-check passed.
        valid: True only when every produced episode resolved to its expected original.
        mismatches: The produced episodes that failed, empty when valid.
        ambiguous_resolved: Produced indices whose content hash also matched another
            original, resolved by the operation's declared survivor order. Recorded for
            transparency; not a failure, because the order is LeRobot's ground truth.
    """

    mapping: dict[int, int]
    valid: bool
    mismatches: tuple[Mismatch, ...]
    ambiguous_resolved: tuple[int, ...] = field(default=())


def resolve_remap(
    original_hashes: dict[int, str],
    produced_hashes: dict[int, str],
    expected_survivors: list[int],
) -> RemapResult:
    """Cross-check a renumber by content hash, for every episode, with no sampling.

    Produced episodes are in the same order LeRobot keeps survivors in, so produced
    episode *j* is expected to carry the content of `expected_survivors[j]`. The check
    reverse-looks-up each produced hash in the original and confirms it resolves to
    that expected original; a hash that resolves elsewhere, to nothing, or a count that
    does not match the survivor list, is a mismatch that fails the whole remap.

    Args:
        original_hashes: Every original episode index to its content hash.
        produced_hashes: Every produced episode index to its content hash.
        expected_survivors: The original indices the operation keeps, in produced order.

    Returns:
        (RemapResult) The new->old mapping and whether the cross-check passed.
    """
    reverse: dict[str, list[int]] = {}
    for old_index, digest in original_hashes.items():
        reverse.setdefault(digest, []).append(old_index)

    mapping: dict[int, int] = {}
    mismatches: list[Mismatch] = []
    ambiguous: list[int] = []

    if len(produced_hashes) != len(expected_survivors):
        # A count mismatch means the operation did not produce the episodes it
        # promised; every produced episode is suspect, so report each position.
        for produced_index in sorted(produced_hashes):
            expected_old = (
                expected_survivors[produced_index]
                if produced_index < len(expected_survivors)
                else -1
            )
            mismatches.append(
                Mismatch(
                    produced_index=produced_index,
                    expected_original_index=expected_old,
                    produced_hash=produced_hashes[produced_index],
                    expected_hash=original_hashes.get(expected_old),
                )
            )
        return RemapResult(mapping={}, valid=False, mismatches=tuple(mismatches))

    for produced_index in range(len(expected_survivors)):
        produced_hash = produced_hashes[produced_index]
        expected_old = expected_survivors[produced_index]
        candidates = reverse.get(produced_hash, [])
        if expected_old in candidates and produced_hash == original_hashes.get(expected_old):
            mapping[produced_index] = expected_old
            if len(candidates) > 1:
                ambiguous.append(produced_index)
        else:
            mismatches.append(
                Mismatch(
                    produced_index=produced_index,
                    expected_original_index=expected_old,
                    produced_hash=produced_hash,
                    expected_hash=original_hashes.get(expected_old),
                )
            )

    valid = not mismatches and len(mapping) == len(expected_survivors)
    return RemapResult(
        mapping=mapping,
        valid=valid,
        mismatches=tuple(mismatches),
        ambiguous_resolved=tuple(ambiguous),
    )


def _read_sidecar_json(store: DatasetStore, episode_index: int) -> dict[str, object] | None:
    """Read one raw sidecar JSON, or None when the episode has no sidecar.

    Reads the raw mapping rather than a typed `EpisodeSidecar` so the report body is
    carried verbatim: WP-3B-12's `read_sidecar` intentionally drops the report on
    read, which would silently strip it from a remapped copy.

    Args:
        store: The source dataset store.
        episode_index: The original episode index.

    Returns:
        (dict | None) The raw sidecar mapping, or None when absent.
    """
    path = store.sidecar_path(episode_index)
    if not path.is_file():
        return None
    body: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return body


def _reindex_sidecar(body: dict[str, object], new_index: int) -> dict[str, object]:
    """Return a sidecar mapping with its episode index rewritten, report preserved.

    Both the top-level `episode_index` and the label's own copy of it are rewritten,
    so a remapped sidecar names one episode consistently.

    Args:
        body: The original sidecar mapping.
        new_index: The new episode index to stamp.

    Returns:
        (dict) The reindexed mapping.
    """
    reindexed = dict(body)
    reindexed[_EPISODE_INDEX_FIELD] = new_index
    label = reindexed.get(_LABEL_KEY)
    if isinstance(label, dict):
        patched_label = dict(label)
        patched_label[_EPISODE_INDEX_FIELD] = new_index
        reindexed[_LABEL_KEY] = patched_label
    return reindexed


class RemapApplyError(RuntimeError):
    """A validated remap did not write back the indices it promised.

    Raised only after `resolve_remap` returned valid, so it signals a write-side
    inconsistency (a sidecar that landed at the wrong index) rather than a content
    mismatch — which `resolve_remap` reports as `INVALID` before any write.
    """


def apply_remap(original_root: Path, produced_root: Path, mapping: dict[int, int]) -> list[int]:
    """Carry each surviving episode's sidecar to its new index, then verify the write.

    For every produced episode whose original had a sidecar, the sidecar is reindexed
    and written under the new index; deleted episodes' sidecars are dropped by never
    being copied. The output is then re-read and each written sidecar's stored index
    is checked to equal its filename index, so the remap is proven on disk, not assumed.

    Args:
        original_root: The immutable original dataset root.
        produced_root: The renumbered output dataset root.
        mapping: Produced (new) index to original (old) index, from `resolve_remap`.

    Returns:
        (list[int]) The produced indices a sidecar was written for, ascending.

    Raises:
        RemapApplyError: When a written sidecar does not carry its own new index.
    """
    source = DatasetStore(original_root)
    destination = DatasetStore(produced_root)
    written: list[int] = []
    for new_index in sorted(mapping):
        old_index = mapping[new_index]
        body = _read_sidecar_json(source, old_index)
        if body is None:
            continue
        destination.ensure_quality_dir()
        reindexed = _reindex_sidecar(body, new_index)
        destination.sidecar_path(new_index).write_text(
            json.dumps(reindexed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written.append(new_index)

    for new_index in written:
        verify = _read_sidecar_json(destination, new_index)
        if verify is None or verify.get(_EPISODE_INDEX_FIELD) != new_index:
            raise RemapApplyError(
                f"sidecar for produced episode {new_index} did not write back its own index"
            )
    return written


def copy_sidecars_identity(original_root: Path, produced_root: Path) -> list[int]:
    """Copy every sidecar to the same index — the identity-preserving-operation path.

    Operations that do not renumber (modify_tasks, remove_feature, recompute_stats,
    reencode, convert) keep episode indices, so their sidecars carry across unchanged.
    Used for the non-renumber outputs where LeRobot wrote a fresh tree without the
    quality sidecars.

    Args:
        original_root: The immutable original dataset root.
        produced_root: The output dataset root.

    Returns:
        (list[int]) The episode indices a sidecar was copied for, ascending.
    """
    source = DatasetStore(original_root)
    destination = DatasetStore(produced_root)
    copied: list[int] = []
    for episode_index in source.episode_indices():
        body = _read_sidecar_json(source, episode_index)
        if body is None:
            continue
        destination.ensure_quality_dir()
        destination.sidecar_path(episode_index).write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        copied.append(episode_index)
    return copied
