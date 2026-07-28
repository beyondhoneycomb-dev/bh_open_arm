"""Every third-party module the source imports is declared in pyproject.toml.

An import that nothing declares works on the machine that happens to carry the package and
nowhere else. That is not a hypothetical: `numpy` (170 files), `mujoco` (50), `openarm_control`
(28), `pyarrow` (21), `cv2`, `PIL`, `scipy` and `pandas` were all undeclared while the suite ran
green here, because they were sitting in the developer's virtualenv. A second machine got an
import error instead of a robot.

The scan is AST-based over the trees the project ships. Two categories are excluded, and the
distinction is the whole point of the checker:

  * The standard library, and this repository's own top-level packages.
  * Modules named as something the code must REFUSE. `backend/can/bind/staticcheck.py` flags
    `import openarm_driver` (01 FR-SYS-010 — it opens its own CAN socket and double-binds with
    LeRobot's bus), and several fixtures exist precisely to be rejected. Declaring those as
    dependencies would install the thing the check exists to keep out.

Import name and distribution name differ often enough that the mapping is explicit rather than
guessed: `cv2` ships in `opencv-python-headless`, `PIL` in `pillow`, `yaml` in `pyyaml`.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from registry import REPO_ROOT

# The trees whose imports must be satisfied by a declared dependency. `tests/` is included: a
# test that cannot be collected is a test nobody runs, which is how CI reported green over a
# suite it never reached.
SCANNED_TREES = ("backend", "sim", "ops", "registry", "contracts", "packages", "dashboard", "tests")

# This repository's own top-level packages — an import of these resolves from the checkout.
FIRST_PARTY = frozenset(
    {
        "backend",
        "sim",
        "ops",
        "registry",
        "contracts",
        "packages",
        "dashboard",
        "targets",
        "deps",
        "tests",
        # WP-0A-03's CTR-OWN@v1 registry. A top-level package like the rest, but outside
        # SCANNED_TREES because nothing under it imports anything undeclared.
        "ownership",
    }
)

# Import name -> distribution name, where they differ.
IMPORT_TO_DISTRIBUTION = {
    "cv2": "opencv-python-headless",
    "PIL": "pillow",
    "yaml": "pyyaml",
    "can": "python-can",
    "attr": "attrs",
}

# Modules the code names in order to refuse them. Declaring any of these would install the exact
# thing its check exists to keep out, so an undeclared import here is correct, not a gap.
REFUSED_MODULES = frozenset(
    {
        # 01 FR-SYS-010 — opens its own CAN socket, double-binds with LeRobot's DamiaoMotorsBus.
        "openarm_driver",
        "openarm_can",
        # 14 FR-OPS-006 — MCAP is the timeseries format; a ROS dependency is refused.
        "rosbag2_py",
        "rclpy",
        # Stage-2 simulator, probed behind try/except and absent by design on this host.
        "isaacsim",
        # 01 §2.7 — named by the driver-ban test to prove it does not over-block. Never imported
        # for its behaviour, so installing it would prove nothing.
        "openarm_ker",
    }
)

PYTHON_GLOB = "*.py"


@dataclass(frozen=True)
class UndeclaredImport:
    """One third-party import with no matching dependency declaration.

    Attributes:
        module: The imported top-level module name.
        distribution: The distribution that would provide it, as far as the mapping knows.
        sites: Repository-relative paths that import it, sorted.
    """

    module: str
    distribution: str
    sites: tuple[str, ...]


def declared_distributions(pyproject: Path) -> frozenset[str]:
    """Return every distribution name pyproject declares, across all dependency groups.

    Args:
        pyproject: Path to `pyproject.toml`.

    Returns:
        (frozenset[str]) Normalised distribution names — lowercase, `_` folded to `-`, so
            `openarm_control` and `openarm-control` are one name.
    """
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    specs: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    return frozenset(_distribution_name(spec) for spec in specs)


def _distribution_name(spec: str) -> str:
    """Reduce a requirement specifier to its normalised distribution name.

    Handles the three shapes this project uses: a bare name, a name with a version specifier,
    and PEP 508 direct-reference form (`lerobot @ git+https://...`).
    """
    name = spec.split("@", 1)[0].strip()
    for separator in ("[", "=", ">", "<", "!", "~", ";", " "):
        name = name.split(separator, 1)[0]
    return name.strip().lower().replace("_", "-")


def scan_imports(root: Path, trees: tuple[str, ...]) -> dict[str, set[str]]:
    """Return every third-party top-level import found under `trees`, mapped to its sites.

    Relative imports are skipped: they resolve inside the checkout by construction.

    Raises:
        SyntaxError: If a scanned file does not parse. An unparsed file is an unscanned file,
            and a partial scan reporting zero gaps reads exactly like a clean one.
    """
    sites: dict[str, set[str]] = {}
    for tree in trees:
        directory = root / tree
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob(PYTHON_GLOB)):
            if "__pycache__" in path.parts:
                continue
            parsed = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            relative = path.relative_to(root).as_posix()
            for module in _imported_roots(parsed):
                sites.setdefault(module, set()).add(relative)
    return sites


def _imported_roots(tree: ast.AST) -> set[str]:
    """Return the top-level module names one parsed module imports."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def undeclared_imports(root: Path = REPO_ROOT) -> list[UndeclaredImport]:
    """Return every third-party import the project makes but does not declare.

    Args:
        root: Repository root.

    Returns:
        (list[UndeclaredImport]) Empty when every import is covered by a dependency group.
    """
    declared = declared_distributions(root / "pyproject.toml")
    standard = set(sys.stdlib_module_names)
    findings: list[UndeclaredImport] = []
    for module, sites in sorted(scan_imports(root, SCANNED_TREES).items()):
        if module in standard or module in FIRST_PARTY or module in REFUSED_MODULES:
            continue
        distribution = IMPORT_TO_DISTRIBUTION.get(module, module).lower().replace("_", "-")
        if distribution in declared:
            continue
        findings.append(
            UndeclaredImport(module=module, distribution=distribution, sites=tuple(sorted(sites)))
        )
    return findings


def main() -> int:
    """Report undeclared imports; exit non-zero when any exist."""
    findings = undeclared_imports()
    for finding in findings:
        shown = ", ".join(finding.sites[:3])
        more = f" (+{len(finding.sites) - 3} more)" if len(finding.sites) > 3 else ""
        print(
            f"UNDECLARED  {finding.module} -> would need '{finding.distribution}' "
            f"in pyproject.toml; imported by {shown}{more}"
        )
    if findings:
        print(f"\n{len(findings)} undeclared third-party import(s) — FAILED")
        return 1
    print("every third-party import is declared in pyproject.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
