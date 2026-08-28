"""Every console script's import closure is in the installed distribution.

A console script gets the interpreter's bin directory on `sys.path` and never the working
directory. A tree an entry point reaches that the wheel omits therefore raises
`ModuleNotFoundError` from every directory including the repository root — and running from the
checkout does not paper over it, which is what made this invisible: every test here imports
`backend.*` as a source tree, so the omission of `contracts` from `packages.find` survived until
`oa-serve` was started for real and died on `from contracts.units import Nm`.

The check is `top_level.txt` against the import closure walked from the entry points, because
those are the two things that have to agree and neither is derived from the other. Importing the
modules is not enough: this process has the checkout on `sys.path`, so every import succeeds here
regardless of what was packaged.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = _REPO_ROOT / "pyproject.toml"

# Trees that exist in the checkout and are deliberately NOT shipped. `tests` is the only one; a
# second name appearing here should be a decision somebody wrote down, not a discovery.
UNSHIPPED = {"tests"}


def _repo_packages() -> set[str]:
    """Top-level directories that are importable python packages in this checkout."""
    found = set()
    for entry in _REPO_ROOT.iterdir():
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        if (entry / "__init__.py").is_file() or any(entry.glob("*/__init__.py")):
            found.add(entry.name)
    return found - UNSHIPPED


def _entry_point_modules() -> list[str]:
    """The module each `[project.scripts]` entry resolves into."""
    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = document["project"]["scripts"]
    return [target.split(":", maxsplit=1)[0] for target in scripts.values()]


def _module_file(module: str) -> Path | None:
    """The source file for a dotted module, or None when it is not a file in this checkout."""
    direct = _REPO_ROOT / Path(*module.split(".")).with_suffix(".py")
    if direct.is_file():
        return direct
    package = _REPO_ROOT / Path(*module.split(".")) / "__init__.py"
    return package if package.is_file() else None


def _closure(start: str, repo_packages: set[str]) -> set[str]:
    """Walk imports from a module and answer every repo top-level package it reaches.

    Follows `__init__.py` as well as the named module: a package's `__init__` runs on the first
    `from pkg.sub import ...`, and that is exactly where this bug landed — `backend.actuation`'s
    `__init__` reaches `contracts` before any code in `serve` runs.
    """
    reached: set[str] = set()
    seen: set[str] = set()
    pending = [start]
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        for candidate in (module, module.rsplit(".", maxsplit=1)[0] if "." in module else module):
            source = _module_file(candidate)
            if source is None:
                continue
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                names: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                elif isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                for name in names:
                    root = name.split(".")[0]
                    if root in repo_packages:
                        reached.add(root)
                        pending.append(name)
    return reached


@pytest.mark.parametrize("module", _entry_point_modules())
def test_every_tree_an_entry_point_reaches_is_shipped(module: str) -> None:
    """The wheel carries what the script imports, or the script dies on start.

    Read from `top_level.txt` rather than from the `include` globs: the globs are a pattern and
    what actually shipped is the answer, and a pattern that matches nothing fails silently.
    """
    top_level = _REPO_ROOT / "bh_open_arm.egg-info" / "top_level.txt"
    if not top_level.is_file():
        pytest.skip("no build metadata in this checkout")
    shipped = {line.strip() for line in top_level.read_text(encoding="utf-8").splitlines() if line}
    repo_packages = _repo_packages()

    missing = sorted(_closure(module, repo_packages) - shipped)

    assert not missing, (
        f"{module} imports {missing}, which `[tool.setuptools.packages.find]` does not ship. "
        "A console script never has the working directory on sys.path, so this is a "
        "ModuleNotFoundError at startup even when run from the repository root."
    )


def test_the_include_list_names_every_shipped_tree() -> None:
    """A tree in the checkout that no glob matches is one nobody decided to leave out.

    The two sides drift in opposite directions and only this compares them: a new top-level
    package is shipped by nobody, and a deleted one leaves a glob matching nothing.
    """
    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    globs = document["tool"]["setuptools"]["packages"]["find"]["include"]
    prefixes = {glob.removesuffix("*") for glob in globs}

    unmatched = sorted(name for name in _repo_packages() if name not in prefixes)

    assert not unmatched, (
        f"{unmatched} are python packages in this checkout that no include glob names. "
        f"Add them to `packages.find` or to this test's UNSHIPPED set with a reason."
    )
