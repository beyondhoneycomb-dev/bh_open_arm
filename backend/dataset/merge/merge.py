"""Verified merge: equality + gain preflight, then the edit-driven merge (WP-3D-06).

`02b` §8.2 WP-3D-06 and `FR-DAT-044`/`045`: a merge runs only after two preflights pass
— the feature-schema/`fps`/`robot_type` equality (`schema.py`) and the gain-profile
equality (`gain.py`). Either failure refuses the merge before any bytes are written, so
a mismatched merge never half-produces a dataset.

The merge itself and its sidecar remap are the committed WP-3D-02 edit module's, imported
not re-implemented (`BATCH-2`, `06` §5.6): the concatenation is `MergeDatasets`' call to
`lerobot merge_datasets`, and each source's per-episode quality sidecar is carried to its
merged index by the same 100% content cross-check (`resolve_remap`) and verified write
(`apply_remap`) a renumber uses. Merge concatenates in source order, so source *s*'s
episodes land at a contiguous offset in the merged dataset; the cross-check proves, per
source, that each merged episode carries the content of the source episode it claims to.
A content mismatch marks the merged output INVALID and aborts, exactly as an edit would.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lerobot.datasets.lerobot_dataset import LeRobotDataset

from backend.dataset.edit import (
    EditContext,
    MergeDatasets,
    apply_remap,
    episode_content_hashes,
    resolve_remap,
)
from backend.dataset.edit.constants import INVALID_MARKER_NAME
from backend.dataset.merge.gain import (
    GainProfile,
    read_gain_profile,
    verify_uniform_gain,
    write_gain_profile,
)
from backend.dataset.merge.schema import DatasetSchema, verify_mergeable_schema


class MergeRefusedError(RuntimeError):
    """Base class for a merge that could not be committed."""


class MergeOutputExistsError(MergeRefusedError):
    """The output path already exists; refusing to write over it (copy-on-write)."""


class MergeRemapError(MergeRefusedError):
    """A merged episode did not carry the content of the source episode it claims to.

    Raised when the per-source content cross-check fails; the merged output is marked
    INVALID and the merge aborts, because a sidecar would otherwise attach a label to
    the wrong episode — the same FAIL_BLOCKING a renumber guards against.

    Attributes:
        source_repo_id: The source whose segment failed the cross-check.
    """

    def __init__(self, source_repo_id: str, detail: str) -> None:
        """Record the failing source and the mismatch detail."""
        super().__init__(
            f"merge content cross-check failed for source {source_repo_id!r}: {detail}; "
            "the merged output is INVALID and the merge is aborted"
        )
        self.source_repo_id = source_repo_id


@dataclass(frozen=True)
class MergeSource:
    """One dataset to merge, identified by its repo id and root.

    Attributes:
        repo_id: The source's stamped repository id.
        root: The source dataset root.
    """

    repo_id: str
    root: Path


@dataclass(frozen=True)
class MergeOrigin:
    """Where a merged episode came from — the reverse of the concatenation.

    Attributes:
        source_index: The source's position in the merge order.
        source_repo_id: The source's repository id.
        source_episode: The episode index within that source.
    """

    source_index: int
    source_repo_id: str
    source_episode: int


@dataclass(frozen=True)
class MergeResult:
    """The result of a committed verified merge.

    Attributes:
        root: The merged dataset root.
        repo_id: The merged dataset's repository id.
        schema: The shared schema every source was proven to carry.
        gain_profile: The shared gain profile, stamped onto the merged output.
        episode_origin: Merged episode index to the source episode it carries.
        remapped_sidecars: The merged episode indices a sidecar was written for.
    """

    root: Path
    repo_id: str
    schema: DatasetSchema
    gain_profile: GainProfile
    episode_origin: dict[int, MergeOrigin]
    remapped_sidecars: tuple[int, ...]


def _write_invalid_marker(root: Path, source_repo_id: str, detail: str) -> None:
    """Stamp the merged output INVALID so it is never taken for a READY training input.

    Reuses WP-3D-05's/WP-3D-02's `EDIT_INVALID` marker name so the integrity gate and
    every reader recognise the same sentinel.

    Args:
        root: The merged output root.
        source_repo_id: The source whose cross-check failed.
        detail: The mismatch detail.
    """
    marker = root / INVALID_MARKER_NAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "operation": "merge",
                "source_repo_id": source_repo_id,
                "reason": (
                    "merged episode content did not match its source; a sidecar would attach "
                    "to the wrong episode (WP-3D-06 FAIL_BLOCKING)"
                ),
                "detail": detail,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def preflight_merge(sources: list[MergeSource]) -> tuple[DatasetSchema, GainProfile]:
    """Verify schema/fps/robot_type and gain-profile equality across the sources.

    Runs before any bytes are written, so a refusal costs nothing. A source with no
    gain tag is the gain-tagless FAIL_BLOCKING (`02b` §8.2 WP-3D-06 ②).

    Args:
        sources: The datasets to merge, in order; at least two.

    Returns:
        (tuple[DatasetSchema, GainProfile]) The shared schema and gain profile.

    Raises:
        MergeSchemaError: On a schema/fps/robot_type divergence.
        GainTagMissingError: When a source carries no gain tag.
        GainProfileMismatchError: When the sources' gain profiles differ.
        GainProfileError: When a gain tag is malformed.
    """
    schemas = [DatasetSchema.from_root(source.repo_id, source.root) for source in sources]
    schema = verify_mergeable_schema(schemas)
    profiles = [read_gain_profile(source.repo_id, source.root) for source in sources]
    gain_profile = verify_uniform_gain(profiles)
    return schema, gain_profile


def _remap_source_segment(
    source: MergeSource,
    source_index: int,
    merged_root: Path,
    merged_hashes: dict[int, str],
    offset: int,
) -> tuple[dict[int, MergeOrigin], list[int]]:
    """Cross-check and remap one source's contiguous segment of the merged dataset.

    Args:
        source: The source whose segment is being remapped.
        source_index: The source's position in the merge order.
        merged_root: The merged dataset root.
        merged_hashes: Every merged episode index to its content hash.
        offset: The merged index the source's first episode landed at.

    Returns:
        (tuple[dict[int, MergeOrigin], list[int]]) The merged-index origin map for this
            segment, and the merged indices a sidecar was written for.

    Raises:
        MergeRemapError: When the segment's content cross-check fails.
    """
    source_dataset = LeRobotDataset(source.repo_id, root=source.root)
    episode_count = source_dataset.meta.total_episodes
    source_hashes = episode_content_hashes(source_dataset)
    segment = {local: merged_hashes[offset + local] for local in range(episode_count)}
    remap = resolve_remap(source_hashes, segment, list(range(episode_count)))
    if not remap.valid:
        detail = (
            f"{len(remap.mismatches)} episode(s) in the merged segment starting at {offset} "
            "did not resolve to their source content"
        )
        _write_invalid_marker(merged_root, source.repo_id, detail)
        raise MergeRemapError(source.repo_id, detail)

    global_mapping = {
        offset + local_new: local_old for local_new, local_old in remap.mapping.items()
    }
    written = apply_remap(source.root, merged_root, global_mapping)
    origins = {
        offset + local_new: MergeOrigin(
            source_index=source_index,
            source_repo_id=source.repo_id,
            source_episode=local_old,
        )
        for local_new, local_old in remap.mapping.items()
    }
    return origins, written


def merge_datasets_verified(
    sources: list[MergeSource], output_repo_id: str, output_dir: Path
) -> MergeResult:
    """Merge datasets after verifying schema and gain equality, remapping sidecars.

    The order of operations is the WP-3D-06 contract: verify mergeability (schema,
    then gain), refuse to write over an existing output, drive the merge through the
    committed `MergeDatasets` edit call, cross-check and remap each source's sidecars,
    then stamp the merged output with the shared gain profile.

    Args:
        sources: The datasets to merge, in order; at least two.
        output_repo_id: The merged dataset's repository id.
        output_dir: Where the merged dataset is written; must not already exist.

    Returns:
        (MergeResult) The merged dataset, its shared schema/gain, and the origin map.

    Raises:
        MergeSchemaError: On a schema/fps/robot_type divergence.
        GainTagMissingError: When a source carries no gain tag (FAIL_BLOCKING).
        GainProfileMismatchError: When the sources' gain profiles differ.
        MergeOutputExistsError: When the output path already exists.
        MergeRemapError: When a merged segment's content cross-check fails.
    """
    if output_dir.exists():
        raise MergeOutputExistsError(
            f"output {output_dir} already exists; refusing to write over it"
        )
    schema, gain_profile = preflight_merge(sources)

    operation = MergeDatasets(
        roots=tuple(source.root for source in sources),
        repo_ids=tuple(source.repo_id for source in sources),
    )
    produced = operation.call(
        EditContext(dataset=None, output_dir=output_dir, repo_id=output_repo_id)
    )
    merged_dataset: Any = next(iter(produced.values()))
    merged_root = Path(merged_dataset.root)
    merged_hashes = episode_content_hashes(merged_dataset)

    expected_total = sum(
        LeRobotDataset(source.repo_id, root=source.root).meta.total_episodes for source in sources
    )
    if merged_dataset.meta.total_episodes != expected_total:
        detail = (
            f"merged dataset has {merged_dataset.meta.total_episodes} episodes, expected "
            f"{expected_total} from the sources"
        )
        _write_invalid_marker(merged_root, output_repo_id, detail)
        raise MergeRemapError(output_repo_id, detail)

    episode_origin: dict[int, MergeOrigin] = {}
    remapped: list[int] = []
    offset = 0
    for source_index, source in enumerate(sources):
        origins, written = _remap_source_segment(
            source, source_index, merged_root, merged_hashes, offset
        )
        episode_origin.update(origins)
        remapped.extend(written)
        offset += LeRobotDataset(source.repo_id, root=source.root).meta.total_episodes

    write_gain_profile(merged_root, gain_profile)

    return MergeResult(
        root=merged_root,
        repo_id=merged_dataset.repo_id,
        schema=schema,
        gain_profile=gain_profile,
        episode_origin=episode_origin,
        remapped_sidecars=tuple(sorted(remapped)),
    )
