"""Work-package manifests, reduced to what the spawn and cancel adapters actually read.

Field names follow `06` §2.2, whose schema is owned by `WP-BOOT-02` and does not exist yet. This
reader therefore validates only the axes this package depends on — stage shape, stage execution
class, stage cancel policy, and the ownership units a fan-out is computed from. It deliberately
does NOT re-check whether `exec_class` is the class its `workflow` derives to: that rule is
`CI-14`, owned by `WP-BOOT-03`, and implementing it twice is how two truths start.

Fan-out width comes from `01` §1.2: an implementation stage's width is the number of exclusive
write units, not the number of targets. Every other shape is pinned to one instance, and for
`SHAPE-MS` that pin is physical rather than a policy choice — there is one rig.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

from ops.cancel.policy import (
    CancelPolicy,
    ExecClass,
    derive_cancel_policy,
    verify_declared_policy,
)

EXCLUSIVE_MODE = "EXCLUSIVE"
_SHAPE_TOKEN = re.compile(r"^(?P<shape>SHAPE-[A-Z]{2})(?:\((?P<width>\d+)\))?$")


class Shape(StrEnum):
    """Workflow shape. The five tokens of `05` §1.1 are the whole vocabulary."""

    CF = "SHAPE-CF"
    IM = "SHAPE-IM"
    IG = "SHAPE-IG"
    MS = "SHAPE-MS"
    HG = "SHAPE-HG"


class ManifestError(Exception):
    """Raised when a manifest cannot be read as a single unambiguous execution plan."""


@dataclass(frozen=True)
class OwnsEntry:
    """One ownership claim of a stage."""

    glob: str
    mode: str


@dataclass(frozen=True)
class Stage:
    """One execution stage of a work package.

    A single-stage package has exactly one of these, built from the manifest's scalar fields.
    """

    index: int
    workflow: Shape
    exec_class: ExecClass
    cancel_policy: CancelPolicy
    owns: tuple[OwnsEntry, ...]

    def exclusive_units(self) -> int:
        """Count the exclusive write units this stage claims.

        Returns:
            (int): Number of `EXCLUSIVE` ownership entries.
        """
        return sum(1 for entry in self.owns if entry.mode == EXCLUSIVE_MODE)

    def fanout(self) -> int:
        """Compute how many instances this stage runs at.

        Returns:
            (int): Instance count; always 1 outside `SHAPE-IM`.
        """
        if self.workflow is not Shape.IM:
            return 1
        return self.exclusive_units()


@dataclass(frozen=True)
class Manifest:
    """A work package's execution plan."""

    wp_id: str
    stages: tuple[Stage, ...]

    def stage(self, index: int) -> Stage:
        """Fetch a stage by index.

        Args:
            index: Zero-based stage index.

        Returns:
            (Stage): The stage at that index.

        Raises:
            ManifestError: No such stage.
        """
        if index < 0 or index >= len(self.stages):
            raise ManifestError(f"{self.wp_id}: no stage at index {index}")
        return self.stages[index]

    def is_multi_stage(self) -> bool:
        """Report whether this package changes execution meaning partway through.

        Returns:
            (bool): True when the manifest declared `phases[]`.
        """
        return len(self.stages) > 1


def _parse_shape(raw: object, wp_id: str) -> tuple[Shape, int | None]:
    """Parse a workflow token, with its optional declared width.

    Args:
        raw: The manifest's workflow value.
        wp_id: Package id, for error messages.

    Returns:
        (tuple[Shape, int | None]): The shape and the width it declared, if any.

    Raises:
        ManifestError: The value is not exactly one token from the five-shape vocabulary. Two
            tokens in one field (`A + B`, `A -> B`) are rejected by `00` §3.2a; multi-stage
            packages say that with `phases[]`.
    """
    if not isinstance(raw, str):
        raise ManifestError(f"{wp_id}: workflow must be a string, got {type(raw).__name__}")
    token = raw.strip()
    match = _SHAPE_TOKEN.match(token)
    if match is None:
        raise ManifestError(
            f"{wp_id}: {token!r} is not a single shape token; multi-stage packages use phases[]"
        )
    try:
        shape = Shape(match.group("shape"))
    except ValueError as error:
        raise ManifestError(f"{wp_id}: {token!r} is outside the five-shape vocabulary") from error
    width = match.group("width")
    return shape, int(width) if width is not None else None


def _parse_owns(raw: object, wp_id: str) -> tuple[OwnsEntry, ...]:
    """Parse an ownership list.

    Args:
        raw: The manifest's owns value; may be absent.
        wp_id: Package id, for error messages.

    Returns:
        (tuple[OwnsEntry, ...]): Parsed ownership claims.

    Raises:
        ManifestError: An entry is not a `{glob, mode}` mapping.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ManifestError(f"{wp_id}: owns must be a list")
    entries: list[OwnsEntry] = []
    for item in raw:
        if not isinstance(item, dict) or "glob" not in item or "mode" not in item:
            raise ManifestError(f"{wp_id}: owns entry must be a mapping with glob and mode")
        entries.append(OwnsEntry(glob=str(item["glob"]), mode=str(item["mode"])))
    return tuple(entries)


def _build_stage(
    index: int,
    workflow: object,
    exec_class_raw: object,
    cancel_policy_raw: object,
    owns_raw: object,
    wp_id: str,
) -> Stage:
    """Assemble and validate one stage.

    Args:
        index: Zero-based stage index.
        workflow: Raw workflow token.
        exec_class_raw: Raw execution class.
        cancel_policy_raw: Raw cancel policy, or None to derive it.
        owns_raw: Raw ownership list.
        wp_id: Package id, for error messages.

    Returns:
        (Stage): The validated stage.

    Raises:
        ManifestError: A value is outside its vocabulary, the declared width disagrees with the
            ownership units it must equal, or a measurement stage claims ownership.
    """
    shape, declared_width = _parse_shape(workflow, wp_id)

    try:
        exec_class = ExecClass(str(exec_class_raw))
    except ValueError as error:
        raise ManifestError(
            f"{wp_id} stage {index}: {exec_class_raw!r} is not an execution class"
        ) from error

    # A declared policy is verified against the class; an undeclared one is derived from it.
    # Either way the stage ends up with the policy its execution class forces.
    if cancel_policy_raw is None:
        cancel_policy = derive_cancel_policy(exec_class)
    else:
        try:
            cancel_policy = CancelPolicy(str(cancel_policy_raw))
        except ValueError as error:
            raise ManifestError(
                f"{wp_id} stage {index}: {cancel_policy_raw!r} is not a cancel policy"
            ) from error
        verify_declared_policy(exec_class, cancel_policy)

    owns = _parse_owns(owns_raw, wp_id)

    # A measurement stage reads and measures; it writes nothing (`00` §3.2a).
    if shape is Shape.MS and owns:
        raise ManifestError(f"{wp_id} stage {index}: SHAPE-MS must own nothing")

    stage = Stage(
        index=index,
        workflow=shape,
        exec_class=exec_class,
        cancel_policy=cancel_policy,
        owns=owns,
    )
    _verify_width(stage, declared_width, wp_id)
    return stage


def _verify_width(stage: Stage, declared_width: int | None, wp_id: str) -> None:
    """Check a declared fan-out width against the width the shape allows.

    Args:
        stage: Stage being validated.
        declared_width: Width parsed from the workflow token, if any.
        wp_id: Package id, for error messages.

    Raises:
        ManifestError: The declaration contradicts the shape's width rule.
    """
    if stage.workflow is not Shape.IM:
        if declared_width is not None and declared_width != 1:
            raise ManifestError(
                f"{wp_id} stage {stage.index}: {stage.workflow.value} runs at width 1, "
                f"manifest declares {declared_width}"
            )
        return

    units = stage.exclusive_units()
    if units == 0:
        raise ManifestError(
            f"{wp_id} stage {stage.index}: SHAPE-IM with no exclusive ownership unit has "
            "nothing to fan out over"
        )
    if declared_width is not None and declared_width != units:
        raise ManifestError(
            f"{wp_id} stage {stage.index}: declared width {declared_width} but owns "
            f"{units} exclusive units"
        )


def parse_manifest(document: dict[str, object]) -> Manifest:
    """Build a manifest from an already-loaded mapping.

    Args:
        document: Manifest mapping.

    Returns:
        (Manifest): The validated manifest.

    Raises:
        ManifestError: The document declares both scalar shape fields and `phases[]`, or
            neither. `00` §3.2a makes those mutually exclusive so that exactly one place
            answers "what is running right now".
    """
    wp_id_raw = document.get("wp_id")
    if not isinstance(wp_id_raw, str) or not wp_id_raw:
        raise ManifestError("manifest has no wp_id")
    wp_id = wp_id_raw

    phases = document.get("phases")
    has_scalar = "workflow" in document or "exec_class" in document

    if phases is not None and has_scalar:
        raise ManifestError(f"{wp_id}: phases[] and scalar workflow/exec_class are exclusive")

    if phases is None:
        if not has_scalar:
            raise ManifestError(f"{wp_id}: manifest declares neither workflow nor phases[]")
        stage = _build_stage(
            index=0,
            workflow=document.get("workflow"),
            exec_class_raw=document.get("exec_class"),
            cancel_policy_raw=document.get("cancel_policy"),
            owns_raw=document.get("owns"),
            wp_id=wp_id,
        )
        return Manifest(wp_id=wp_id, stages=(stage,))

    if not isinstance(phases, list) or not phases:
        raise ManifestError(f"{wp_id}: phases[] must be a non-empty list")

    stages: list[Stage] = []
    for index, raw in enumerate(phases):
        if not isinstance(raw, dict):
            raise ManifestError(f"{wp_id}: phases[{index}] must be a mapping")
        if "cancel_policy" not in raw:
            raise ManifestError(f"{wp_id}: phases[{index}] must declare cancel_policy")
        stages.append(
            _build_stage(
                index=index,
                workflow=raw.get("workflow"),
                exec_class_raw=raw.get("exec_class"),
                cancel_policy_raw=raw.get("cancel_policy"),
                owns_raw=raw.get("owns"),
                wp_id=wp_id,
            )
        )
    return Manifest(wp_id=wp_id, stages=tuple(stages))


def load_manifest(path: Path) -> Manifest:
    """Read and validate a manifest file.

    Args:
        path: Path to a YAML or JSON manifest.

    Returns:
        (Manifest): The validated manifest.

    Raises:
        ManifestError: The file is not a mapping.
    """
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ManifestError(f"{path}: manifest must be a mapping")
    return parse_manifest(document)
