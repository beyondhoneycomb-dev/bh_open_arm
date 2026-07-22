"""Static guards CTR-CAM@v1 must pass: no primitive fork, no restated geometry.

Two build-blocking scans, both machinery rather than the contract itself (they are
`EXCLUSIVE`, not `CONTRACT_FROZEN`):

* `check_no_primitive_redefinition` — the `02b` §5.2 WP-3A-00 ② single-definition
  rule, applied to this contract's own modules. It delegates to the `CTR-PRIM@v1`
  scanner, so the reserved set has one owner; a camera schema that declared its own
  `CameraSlotKey` or `FrameType` would be caught here.
* `check_no_resolution_fps_redeclaration` — the `02b` §5.2 WP-3A-01 ① rule that
  resolution and fps live in exactly one place, the `CameraSpec` dict. Any layer
  that binds `width`/`height`/`fps`/`resolution`/`framerate` to a numeric literal
  has restated the geometry the dict already owns, and is flagged. A bare field
  annotation (`width: int | None`) carries no literal and is the sanctioned dict;
  a keyword argument (`CameraSpec(width=640)`) is a call, not a binding, and is fine.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from contracts.prim import Redefinition, check_no_redefinition

# The geometry names the `CameraSpec` dict owns. Any binding of one of these to a
# fixed number outside the dict is a restatement of resolution or fps.
RESERVED_GEOMETRY_NAMES = frozenset(
    {"width", "height", "fps", "resolution", "framerate", "frame_rate"}
)


def check_no_primitive_redefinition(paths: list[Path]) -> list[Redefinition]:
    """Find any `CTR-PRIM@v1` primitive this contract defines instead of imports.

    Args:
        paths: The camera-registry Python modules to scan.

    Returns:
        (list[Redefinition]) One entry per redefined primitive, empty when clean.
    """
    return check_no_redefinition(paths)


@dataclass(frozen=True)
class GeometryRedeclaration:
    """One resolution or fps value restated outside the `CameraSpec` dict.

    Attributes:
        path: File the redeclaration was found in.
        line: 1-indexed line of the binding.
        name: The geometry name that was bound to a literal.
    """

    path: str
    line: int
    name: str


def _reserved_literal_target(target: ast.expr, value: ast.expr | None) -> str | None:
    """Return a reserved geometry name bound to a numeric literal, or None.

    Args:
        target: An assignment target expression.
        value: The bound value, or None for a bare annotation.

    Returns:
        (str | None) The reserved name when it is bound to a number, else None.
    """
    if not isinstance(target, ast.Name) or target.id.lower() not in RESERVED_GEOMETRY_NAMES:
        return None
    if (
        isinstance(value, ast.Constant)
        and isinstance(value.value, (int, float))
        and not isinstance(value.value, bool)
    ):
        return target.id
    return None


def scan_geometry_redeclarations(path: Path) -> list[GeometryRedeclaration]:
    """Find geometry names bound to a numeric literal anywhere in one module.

    The whole tree is walked, not just the top level: a hardcoded `fps = 30` inside
    a function or a non-`CameraSpec` class restates the geometry just as a
    module-level one does.

    Args:
        path: Python file to scan.

    Returns:
        (list[GeometryRedeclaration]) One entry per restated geometry literal.
    """
    hits: list[GeometryRedeclaration] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = _reserved_literal_target(target, node.value)
                if name is not None:
                    hits.append(GeometryRedeclaration(str(path), node.lineno, name))
        elif isinstance(node, ast.AnnAssign):
            name = _reserved_literal_target(node.target, node.value)
            if name is not None:
                hits.append(GeometryRedeclaration(str(path), node.lineno, name))
    return hits


def check_no_resolution_fps_redeclaration(paths: list[Path]) -> list[GeometryRedeclaration]:
    """Scan several modules for resolution or fps restated outside the dict.

    Args:
        paths: Python files to scan.

    Returns:
        (list[GeometryRedeclaration]) Every restated geometry literal, in path
            then source order.
    """
    hits: list[GeometryRedeclaration] = []
    for path in sorted(paths):
        hits.extend(scan_geometry_redeclarations(path))
    return hits
