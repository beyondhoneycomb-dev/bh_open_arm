"""The static scan behind WP-2B-09 acceptance ②: no code binds the two scales to one variable.

Detection (100%) and control (partial) scales are independent only if nothing in the source ties
them together. This module reads the abstract syntax tree of the files it is given and reports
every place a single value reaches both a `DetectionModelScales` and a `ControlCompensationScales`
construction. It is a pure-AST check with no runtime dependency on the dynamics stack, so it stays
in the light lane and a downstream consumer (WP-2C-01, the control loop) can point it at its own
tree without importing mujoco.

Three bindings it recognises, each anchored on the two concrete scale types rather than on a name
heuristic:

* shared-variable — one variable supplies a scale keyword to both constructions (`friction_scale=s`
  on each). This is the literal "한 변수로 묶인" the acceptance criterion names.
* cross-read — a scale keyword of one construction reads a scale field off a value of the other
  type (`DetectionModelScales(friction_scale=control.friction_scale)`).
* attribute-copy — a scale field of one type's instance is assigned from a scale field of the
  other's (`detection.friction_scale = control.friction_scale`).

A finding is `FAIL_BLOCKING` (FR-SAF-035): the control coefficient 0.3 becomes the detection
model's friction scale, and the fraction it does not compensate becomes the residual's floor.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from backend.compscale.errors import ScaleSeparationError

DETECTION_TYPE = "DetectionModelScales"
CONTROL_TYPE = "ControlCompensationScales"
SCALE_TYPES = frozenset({DETECTION_TYPE, CONTROL_TYPE})
SCALE_FIELDS = frozenset({"friction_scale", "coriolis_scale"})

KIND_SHARED_VARIABLE = "shared-variable"
KIND_CROSS_READ = "cross-read"
KIND_ATTRIBUTE_COPY = "attribute-copy"


@dataclass(frozen=True)
class ScaleBinding:
    """One place where the detection and control scales are bound together.

    Attributes:
        path: Root-relative or absolute POSIX path of the offending file.
        line: 1-indexed line of the binding.
        kind: One of the `KIND_*` binding forms.
        detail: Human-readable description naming the bound symbol.
    """

    path: str
    line: int
    kind: str
    detail: str


def find_scale_bindings(paths: Iterable[Path]) -> tuple[ScaleBinding, ...]:
    """Scan the given Python files and return every detection/control scale binding.

    Args:
        paths: Python source files to scan. A non-`.py` or unreadable path is skipped.

    Returns:
        (tuple[ScaleBinding, ...]) Bindings found, in file-then-line order.
    """
    findings: list[ScaleBinding] = []
    for path in paths:
        if path.suffix != ".py" or not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        findings.extend(_scan_tree(tree, path.as_posix()))
    return tuple(findings)


def compscale_package_files() -> tuple[Path, ...]:
    """Return the Python sources of the compscale package itself."""
    return tuple(sorted(Path(__file__).resolve().parent.glob("*.py")))


def assert_scales_independent(paths: Iterable[Path] | None = None) -> None:
    """Raise if any scanned file binds the detection and control scales to one variable.

    Args:
        paths: Files to scan; defaults to the compscale package's own sources.

    Raises:
        ScaleSeparationError: If one or more bindings are found. The message lists each so a
            reviewer sees the exact site, and the raise makes the FAIL_BLOCKING branch bite in
            code rather than only in a document.
    """
    targets = tuple(paths) if paths is not None else compscale_package_files()
    bindings = find_scale_bindings(targets)
    if bindings:
        lines = "\n".join(f"  {b.path}:{b.line} [{b.kind}] {b.detail}" for b in bindings)
        raise ScaleSeparationError(
            f"detection and control compensation scales are bound in {len(bindings)} place(s); "
            f"they must stay independent (FR-SAF-035):\n{lines}"
        )


def _binding_order(binding: ScaleBinding) -> tuple[int, str]:
    """Sort key placing bindings in line-then-kind order for a stable report."""
    return (binding.line, binding.kind)


def _scan_tree(tree: ast.Module, path: str) -> list[ScaleBinding]:
    """Return every scale binding in one parsed module."""
    var_types = _variable_scale_types(tree)
    findings: list[ScaleBinding] = []
    findings.extend(_construction_bindings(tree, path, var_types))
    findings.extend(_attribute_copy_bindings(tree, path, var_types))
    return sorted(findings, key=_binding_order)


def _variable_scale_types(tree: ast.Module) -> dict[str, str]:
    """Map each variable assigned a scale set to the scale type it holds.

    Covers direct construction (`x = ControlCompensationScales(...)`), the classmethod builders
    (`x = DetectionModelScales.full()`), and annotated names (`x: DetectionModelScales`).
    """
    var_types: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            produced = _produced_type(node.value)
            if produced:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_types[target.id] = produced
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            annotated = _annotation_type(node.annotation)
            if annotated:
                var_types[node.target.id] = annotated
    return var_types


def _construction_bindings(
    tree: ast.Module, path: str, var_types: dict[str, str]
) -> list[ScaleBinding]:
    """Report shared-variable and cross-read bindings across scale constructions."""
    findings: list[ScaleBinding] = []
    name_lines: dict[str, dict[str, int]] = {DETECTION_TYPE: {}, CONTROL_TYPE: {}}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        ctor_type = _direct_ctor_type(node)
        if not ctor_type:
            continue
        for keyword in node.keywords:
            if keyword.arg not in SCALE_FIELDS:
                continue
            value = keyword.value
            other = _other_type_of_scale_read(value, ctor_type, var_types)
            if other:
                findings.append(
                    ScaleBinding(
                        path=path,
                        line=node.lineno,
                        kind=KIND_CROSS_READ,
                        detail=(
                            f"{ctor_type}.{keyword.arg} reads a scale field off a "
                            f"{other} value — the two scales are not independent"
                        ),
                    )
                )
            if isinstance(value, ast.Name):
                name_lines[ctor_type].setdefault(value.id, node.lineno)
    for name in sorted(set(name_lines[DETECTION_TYPE]) & set(name_lines[CONTROL_TYPE])):
        findings.append(
            ScaleBinding(
                path=path,
                line=min(name_lines[DETECTION_TYPE][name], name_lines[CONTROL_TYPE][name]),
                kind=KIND_SHARED_VARIABLE,
                detail=(
                    f"variable {name!r} sets a scale on both {DETECTION_TYPE} and {CONTROL_TYPE}"
                ),
            )
        )
    return findings


def _attribute_copy_bindings(
    tree: ast.Module, path: str, var_types: dict[str, str]
) -> list[ScaleBinding]:
    """Report a scale field of one type's instance assigned from the other's."""
    findings: list[ScaleBinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        source_type = _scale_read_type(node.value, var_types)
        if not source_type:
            continue
        for target in node.targets:
            target_type = _scale_write_type(target, var_types)
            if target_type and target_type != source_type:
                findings.append(
                    ScaleBinding(
                        path=path,
                        line=node.lineno,
                        kind=KIND_ATTRIBUTE_COPY,
                        detail=(
                            f"a {target_type} scale field is assigned from a {source_type} "
                            "scale field"
                        ),
                    )
                )
    return findings


def _direct_ctor_type(call: ast.Call) -> str | None:
    """Return the scale type a call constructs directly, or None.

    Matches `DetectionModelScales(...)` and `module.DetectionModelScales(...)`, but not the
    classmethod builders, which take no scale keywords.
    """
    func = call.func
    if isinstance(func, ast.Name) and func.id in SCALE_TYPES:
        return func.id
    if isinstance(func, ast.Attribute) and func.attr in SCALE_TYPES:
        return func.attr
    return None


def _produced_type(call: ast.Call) -> str | None:
    """Return the scale type a call yields, including the classmethod builders."""
    direct = _direct_ctor_type(call)
    if direct:
        return direct
    func = call.func
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in SCALE_TYPES
    ):
        return func.value.id
    return None


def _annotation_type(annotation: ast.expr) -> str | None:
    """Return the scale type named by a variable annotation, or None."""
    if isinstance(annotation, ast.Name) and annotation.id in SCALE_TYPES:
        return annotation.id
    return None


def _other_type_of_scale_read(
    value: ast.expr, ctor_type: str, var_types: dict[str, str]
) -> str | None:
    """Return the scale type a value reads a scale field from, when it differs from `ctor_type`.

    Recognises reading off a typed variable (`control.friction_scale`) and off a fresh
    construction (`ControlCompensationScales().friction_scale`).
    """
    read_type = _scale_read_type(value, var_types)
    if read_type and read_type != ctor_type:
        return read_type
    return None


def _scale_read_type(value: ast.expr, var_types: dict[str, str]) -> str | None:
    """Return the scale type of the object a scale-field read targets, or None.

    A "scale-field read" is `<obj>.friction_scale` / `<obj>.coriolis_scale` where `<obj>` is a
    variable of a known scale type or a scale construction.
    """
    if not (isinstance(value, ast.Attribute) and value.attr in SCALE_FIELDS):
        return None
    base = value.value
    if isinstance(base, ast.Name):
        return var_types.get(base.id)
    if isinstance(base, ast.Call):
        return _produced_type(base)
    return None


def _scale_write_type(target: ast.expr, var_types: dict[str, str]) -> str | None:
    """Return the scale type of the object a scale-field assignment targets, or None."""
    if not (isinstance(target, ast.Attribute) and target.attr in SCALE_FIELDS):
        return None
    if isinstance(target.value, ast.Name):
        return var_types.get(target.value.id)
    return None
