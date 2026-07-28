"""Nothing the source imports is missing from pyproject.toml, and the checker can tell.

The zero-finding assertion at the end is worth nothing on its own — a scan that looks for nothing
also finds nothing. So the positive controls come first: a planted undeclared import must be
reported, and the two exclusion categories must keep working, because over-reporting here would
push someone to declare `openarm_driver` as a dependency and install the exact package
`01` FR-SYS-010 exists to keep off the canonical path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from registry import REPO_ROOT
from registry.env.declared_imports import (
    IMPORT_TO_DISTRIBUTION,
    REFUSED_MODULES,
    declared_distributions,
    scan_imports,
    undeclared_imports,
)

# Packages the working environment is known to need; a regression that drops one from pyproject
# would otherwise only surface on a second machine.
_MUST_BE_DECLARED = (
    "numpy",
    "mujoco",
    "openarm-control",
    "openarm-mujoco",
    "mink",
    "pyarrow",
    "scipy",
    "pandas",
    "opencv-python-headless",
    "pillow",
    "lerobot",
    "python-can",
    "mcap",
    "pyyaml",
    "jsonschema",
)


def _tree(tmp_path: Path, body: str, *, pyproject: str) -> Path:
    """Write a one-module project and return its root."""
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "module.py").write_text(body, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return tmp_path


_EMPTY_PROJECT = '[project]\nname = "x"\nversion = "0"\ndependencies = []\n'


def test_an_undeclared_import_is_reported(tmp_path: Path) -> None:
    """The whole point: an import nothing declares is a finding, with its site."""
    root = _tree(tmp_path, "import redis\n", pyproject=_EMPTY_PROJECT)

    findings = undeclared_imports(root)

    assert [f.module for f in findings] == ["redis"]
    assert findings[0].sites == ("backend/module.py",)


def test_a_declared_import_is_not_reported(tmp_path: Path) -> None:
    """Declaring it in any group clears it — the check is about coverage, not placement."""
    project = '[project]\nname = "x"\nversion = "0"\ndependencies = ["redis>=5"]\n'
    root = _tree(tmp_path, "import redis\n", pyproject=project)

    assert undeclared_imports(root) == []


def test_an_optional_group_counts_as_declared(tmp_path: Path) -> None:
    """`[robot]` is where this project puts its heavy stack, so it must clear the check."""
    project = (
        '[project]\nname = "x"\nversion = "0"\ndependencies = []\n'
        '[project.optional-dependencies]\nrobot = ["redis>=5"]\n'
    )
    root = _tree(tmp_path, "import redis\n", pyproject=project)

    assert undeclared_imports(root) == []


def test_the_standard_library_is_not_a_dependency(tmp_path: Path) -> None:
    """A stdlib import must never be reported, or the fix would be to pip-install `pathlib`."""
    root = _tree(tmp_path, "import json\nimport pathlib\n", pyproject=_EMPTY_PROJECT)

    assert undeclared_imports(root) == []


@pytest.mark.parametrize("module", sorted(REFUSED_MODULES))
def test_a_module_the_code_refuses_is_not_a_dependency(tmp_path: Path, module: str) -> None:
    """Declaring these would install the thing their own check exists to keep out.

    `openarm_driver` is the sharp case: `01` FR-SYS-010 bans it on the canonical path because it
    opens its own CAN socket and double-binds with LeRobot's bus, and
    `backend/can/bind/staticcheck.py` fails the build on its import.
    """
    root = _tree(tmp_path, f"import {module}\n", pyproject=_EMPTY_PROJECT)

    assert undeclared_imports(root) == []


def test_a_distribution_named_differently_from_its_import_is_matched(tmp_path: Path) -> None:
    """`import cv2` is satisfied by `opencv-python-headless`, and the mapping must be used."""
    project = (
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["opencv-python-headless>=4.10"]\n'
    )
    root = _tree(tmp_path, "import cv2\n", pyproject=project)

    assert undeclared_imports(root) == []


def test_underscore_and_hyphen_spellings_are_one_name(tmp_path: Path) -> None:
    """`openarm_control` in pyproject and `openarm-control` on PyPI are the same distribution."""
    project = '[project]\nname = "x"\nversion = "0"\ndependencies = ["openarm_control==0.1.0"]\n'
    root = _tree(tmp_path, "import openarm_control\n", pyproject=project)

    assert undeclared_imports(root) == []


def test_a_git_direct_reference_is_read_as_its_distribution_name(tmp_path: Path) -> None:
    """LeRobot is declared as `lerobot @ git+https://...`; the name is still `lerobot`."""
    project = (
        '[project]\nname = "x"\nversion = "0"\n'
        'dependencies = ["lerobot @ git+https://github.com/huggingface/lerobot@abc123"]\n'
    )
    root = _tree(tmp_path, "import lerobot\n", pyproject=project)

    assert undeclared_imports(root) == []


def test_an_unparsable_file_is_raised_not_skipped(tmp_path: Path) -> None:
    """A skipped file makes the finding count a lower bound that still reads as zero."""
    root = _tree(tmp_path, "import (\n", pyproject=_EMPTY_PROJECT)

    with pytest.raises(SyntaxError):
        undeclared_imports(root)


def test_this_repository_declares_every_import_it_makes() -> None:
    """The live assertion. Guarded against scanning nothing, the way the count could lie."""
    scanned = scan_imports(REPO_ROOT, ("backend", "sim", "ops", "registry", "tests"))
    assert "numpy" in scanned, "the scan reached no source: a zero finding count would be empty"

    findings = undeclared_imports()

    assert findings == [], "\n".join(
        f"{f.module} -> needs '{f.distribution}'; e.g. {f.sites[0]}" for f in findings
    )


@pytest.mark.parametrize("distribution", _MUST_BE_DECLARED)
def test_the_working_environment_stays_declared(distribution: str) -> None:
    """Each of these was, or nearly was, present only in one developer's virtualenv."""
    assert distribution in declared_distributions(REPO_ROOT / "pyproject.toml")


def test_every_mapped_import_name_differs_from_its_distribution() -> None:
    """A mapping entry that repeats the import name is noise the lookup already handles."""
    for module, distribution in IMPORT_TO_DISTRIBUTION.items():
        assert module.lower().replace("_", "-") != distribution.lower(), module
