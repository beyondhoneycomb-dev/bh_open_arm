"""The copy-on-write edit engine — original immutable, output verified (WP-3D-02).

This is the resolution of `FR-DAT-022` recorded for this band: **copy-on-write, the
original is immutable** (`02b` §8.2 WP-3D-02). Every edit either writes a new dataset
from the untouched original, or — for the operations LeRobot mutates in place
(`modify_tasks`, `recompute_stats`, `reencode`) — copies the original first and mutates
the copy. The engine never writes back to the original's root.

The order is the acceptance in `02b` §8.2 WP-3D-02:

1. build the pre-commit preview (④), reading the original only;
2. refuse to start unless the filesystem can hold the original and the new version at
   once (⑥, §8.3 "원본과 새 버전이 동시에 존재");
3. run the operation under CoW;
4. for a renumber, remap the sidecars and verify the 100% content cross-check — a
   mismatch marks the output INVALID and aborts (①②③); for an identity-preserving
   operation, carry the sidecars across unchanged;
5. load the produced dataset once to prove it is readable (⑤).

The operations themselves are `lerobot-edit-dataset` calls (`operations.py`); this
module is only the policy around them.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lerobot.datasets.lerobot_dataset import LeRobotDataset

from backend.dataset.edit.constants import (
    COW_REQUIRED_FREE_MULTIPLE,
    INVALID_MARKER_NAME,
)
from backend.dataset.edit.content_hash import episode_content_hashes
from backend.dataset.edit.operations import EditContext, EditOperation
from backend.dataset.edit.preview import EditPreview, build_preview
from backend.dataset.edit.remap import (
    RemapResult,
    apply_remap,
    copy_sidecars_identity,
    resolve_remap,
)


class EditError(RuntimeError):
    """Base class for a copy-on-write edit that could not be committed."""


class CowInPlaceError(EditError):
    """The output path would overwrite the original, breaking copy-on-write."""


class CowDiskError(EditError):
    """The filesystem cannot hold the original and the new version at once.

    Attributes:
        required_bytes: The free space the edit needs (the original's size).
        available_bytes: The free space actually present.
    """

    def __init__(self, required_bytes: int, available_bytes: int) -> None:
        """Record the required and available free space in the message."""
        super().__init__(
            f"copy-on-write needs {required_bytes} bytes free for the coexisting copy, "
            f"but only {available_bytes} are available"
        )
        self.required_bytes = required_bytes
        self.available_bytes = available_bytes


class DelegatedOperationError(EditError):
    """A cross-dataset operation (merge) is owned by WP-3D-06, not driven here."""


class RemapMismatchError(EditError):
    """A renumber's sidecar cross-check failed; the output is INVALID and the op aborts.

    Attributes:
        output_name: The output whose cross-check failed.
        result: The failing `RemapResult`, carrying the per-episode mismatches.
    """

    def __init__(self, output_name: str, result: RemapResult) -> None:
        """Record the failing output and its mismatch detail."""
        super().__init__(
            f"sidecar content cross-check failed for output {output_name!r}: "
            f"{len(result.mismatches)} episode(s) did not resolve to their expected original; "
            "a remap-less renumber attaches a label to the wrong episode"
        )
        self.output_name = output_name
        self.result = result


@dataclass(frozen=True)
class EditOutput:
    """One committed output dataset.

    Attributes:
        output_name: The output name (a split name, or the single output key).
        root: The output dataset root.
        repo_id: The output repository id.
        episode_mapping: Produced episode index to original episode index.
        remapped_sidecars: The produced episode indices a sidecar was written for.
    """

    output_name: str
    root: Path
    repo_id: str
    episode_mapping: dict[int, int]
    remapped_sidecars: list[int]


@dataclass(frozen=True)
class EditResult:
    """The result of a committed copy-on-write edit.

    Attributes:
        preview: The pre-commit preview, per output.
        outputs: The committed outputs, per output name.
    """

    preview: dict[str, EditPreview]
    outputs: dict[str, EditOutput]


def _directory_size(root: Path) -> int:
    """Return the total byte size of a directory tree.

    Args:
        root: The directory to size.

    Returns:
        (int) The sum of file sizes under the directory.
    """
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _nearest_existing(path: Path) -> Path:
    """Return the nearest existing ancestor of a path (itself if it exists).

    Args:
        path: A path that may not exist yet.

    Returns:
        (Path) The closest ancestor that exists on disk.
    """
    current = path
    while not current.exists():
        current = current.parent
    return current


def disk_precheck(original_root: Path, output_dir: Path) -> None:
    """Refuse the edit unless the original and the new version can coexist on disk.

    Copy-on-write keeps the original while writing the new version, so the output
    filesystem must have at least the original's size free (`02b` §8.2 WP-3D-02 ⑥).
    The new version is never larger than the original, so its size is a safe floor.

    Args:
        original_root: The original dataset root.
        output_dir: Where the new version will be written.

    Raises:
        CowDiskError: When the free space is below the original's size.
    """
    required = int(_directory_size(original_root) * COW_REQUIRED_FREE_MULTIPLE)
    available = shutil.disk_usage(_nearest_existing(output_dir)).free
    if available < required:
        raise CowDiskError(required_bytes=required, available_bytes=available)


def _write_invalid_marker(root: Path, output_name: str, result: RemapResult) -> None:
    """Stamp an output as INVALID so it is never taken for a READY training input.

    Args:
        root: The output dataset root.
        output_name: The output name.
        result: The failing cross-check result.
    """
    marker = root / INVALID_MARKER_NAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "output_name": output_name,
                "reason": (
                    "sidecar content cross-check failed; a label would attach to the wrong "
                    "episode (WP-3D-02 FAIL_BLOCKING)"
                ),
                "mismatches": [
                    {
                        "produced_index": mismatch.produced_index,
                        "expected_original_index": mismatch.expected_original_index,
                        "produced_hash": mismatch.produced_hash,
                        "expected_hash": mismatch.expected_hash,
                    }
                    for mismatch in result.mismatches
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _execute(
    operation: EditOperation,
    original: Any,
    original_root: Path,
    repo_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the operation under copy-on-write and return its produced datasets.

    For an in-place operation the original is copied first and the copy is mutated;
    for a new-output operation the untouched original is read and a new dataset is
    written. Either way the original's root is never written to.

    Args:
        operation: The edit operation.
        original: The loaded original dataset.
        original_root: The original dataset root.
        repo_id: The output repository id.
        output_dir: The output directory.

    Returns:
        (dict[str, Any]) Output name to produced `LeRobotDataset`.
    """
    if operation.policy.in_place:
        # Copy first: the underlying op rewrites the dataset it is handed, so it must
        # be handed the copy. The original stays byte-for-byte unchanged.
        shutil.copytree(original_root, output_dir)
        copy = LeRobotDataset(repo_id, root=output_dir)
        return operation.call(EditContext(dataset=copy, output_dir=output_dir, repo_id=repo_id))
    return operation.call(EditContext(dataset=original, output_dir=output_dir, repo_id=repo_id))


def commit_edit(
    original_root: Path,
    repo_id: str,
    operation: EditOperation,
    output_dir: Path,
) -> EditResult:
    """Commit a copy-on-write edit, verifying the sidecar remap 100% on a renumber.

    Args:
        original_root: The original dataset root, left immutable.
        repo_id: The source (and output) repository id.
        operation: The edit operation to apply.
        output_dir: The directory the new version is written under (its base, for
            split); must not already exist.

    Returns:
        (EditResult) The preview and the committed outputs.

    Raises:
        DelegatedOperationError: For a cross-dataset operation (merge).
        CowInPlaceError: When the output path would overwrite the original.
        CowDiskError: When the original and new version cannot coexist on disk.
        RemapMismatchError: When a renumber's content cross-check fails; the output is
            marked INVALID and the edit aborts.
    """
    if operation.policy.cross_dataset:
        raise DelegatedOperationError(
            f"operation {operation.name!r} spans datasets; its remap is owned by WP-3D-06"
        )
    if output_dir.resolve() == original_root.resolve():
        raise CowInPlaceError(
            f"output {output_dir} is the original root; copy-on-write forbids overwriting it"
        )
    if output_dir.exists():
        raise CowInPlaceError(f"output {output_dir} already exists; refusing to write over it")

    original = LeRobotDataset(repo_id, root=original_root)
    preview = build_preview(original, operation)
    disk_precheck(original_root, output_dir)

    produced = _execute(operation, original, original_root, repo_id, output_dir)

    outputs: dict[str, EditOutput] = {}
    original_hashes: dict[int, str] | None = None
    survivors_by_output = operation.expected_survivors(original)
    for output_name, produced_dataset in produced.items():
        produced_root = Path(produced_dataset.root)
        if operation.policy.renumbers:
            if original_hashes is None:
                original_hashes = episode_content_hashes(original)
            produced_hashes = episode_content_hashes(produced_dataset)
            remap = resolve_remap(
                original_hashes, produced_hashes, survivors_by_output[output_name]
            )
            if not remap.valid:
                _write_invalid_marker(produced_root, output_name, remap)
                raise RemapMismatchError(output_name, remap)
            remapped = apply_remap(original_root, produced_root, remap.mapping)
            mapping = remap.mapping
        else:
            remapped = copy_sidecars_identity(original_root, produced_root)
            mapping = {i: i for i in range(produced_dataset.meta.total_episodes)}

        # Prove the output loads once, as a dataset, after the edit (acceptance ⑤).
        reloaded = LeRobotDataset(produced_dataset.repo_id, root=produced_root)
        outputs[output_name] = EditOutput(
            output_name=output_name,
            root=produced_root,
            repo_id=reloaded.repo_id,
            episode_mapping=mapping,
            remapped_sidecars=remapped,
        )

    return EditResult(preview=preview, outputs=outputs)
