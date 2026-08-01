"""The operator guide's hook table is checked against the tree it describes.

`docs/guide/05` tells a person at the bench to point an environment variable at a capture
directory and re-run pytest. Nothing in this repository used to read that guide, so a row
could name a variable no code reads, a test path that does not exist, or a hook that cannot
fire — and the suite stayed green while the operator believed a real capture had been
verified. This module is that missing check.

Four claims, each failable:

- every documented variable is one the tree actually reads (a named constant, not prose);
- every documented test path exists;
- every variable the tree reads is documented — so the guide cannot fall behind the code;
- the row's declared hook status matches how the test directory behaves.

The status claim is the load-bearing one. `수집시점` means the test directory reads the
environment while pytest is collecting, which is what makes a supplied value change the run;
`미연결` means it does not, and the guide says so in the operator's own words. The check is
per test directory rather than per variable: it asserts that the directory reads the
environment at collection time, not which variable it read. Two directories carry two hooks
each (`tests/wp0b04`, `tests/wp0b06`) and in both the coarser claim is still true of each.

This module lives under `tests/wp2c03` because that is the collision-threshold row — the one
where believing an unverified capture matters most — and no work package owns `docs/guide/**`
yet. It checks every row, not just that one.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUIDE_DIR = _REPO_ROOT / "docs" / "guide"
_STEP_GUIDE = _GUIDE_DIR / "05-실기-검증-단계별-실행안내.md"

# Where an environment variable that drives a deferred acceptance may be defined. Test trees
# are excluded on purpose: a name only a test knows is a name no operator can use.
_SOURCE_TREES = ("backend", "ops", "contracts", "scripts")

# The status column of the hook table, and what each value promises the operator.
_STATUS_COLLECTION_TIME = "수집시점"
_STATUS_NOT_WIRED = "미연결"
_STATUS_TOOL_PATH = "도구경로"
_STATUS_IN_TEST_BODY = "본문실행"
_STATUSES = frozenset(
    {_STATUS_COLLECTION_TIME, _STATUS_NOT_WIRED, _STATUS_TOOL_PATH, _STATUS_IN_TEST_BODY}
)

_ENV_NAME = re.compile(r"OPENARM_[A-Z0-9_]+")
_TABLE_ROW = re.compile(
    r"^\|\s*`(OPENARM_[A-Z0-9_]+)`\s*\|(.+?)\|\s*(\S+)\s*\|(.*?)\|\s*$", re.MULTILINE
)
_PATH_CELL = re.compile(r"`([^`]+)`")
_COMMAND_LINE = re.compile(r"^(OPENARM_[A-Z0-9_]+)=\S+\s+pytest\s+(.+)$", re.MULTILINE)


class _Row:
    """One parsed hook-table row.

    Attributes:
        env_var: The environment variable name.
        test_dirs: Repository-relative test paths the row sends the operator to.
        status: The declared hook status, one of `_STATUSES`.
    """

    def __init__(self, env_var: str, test_dirs: tuple[str, ...], status: str) -> None:
        self.env_var = env_var
        self.test_dirs = test_dirs
        self.status = status


def _guide_text() -> str:
    return _STEP_GUIDE.read_text(encoding="utf-8")


def _rows() -> tuple[_Row, ...]:
    """Parse the hook table out of the step guide.

    Returns:
        (tuple[_Row, ...]) Every row, in document order.
    """
    parsed = tuple(
        _Row(
            env_var=match.group(1),
            test_dirs=tuple(_PATH_CELL.findall(match.group(2))),
            status=match.group(3),
        )
        for match in _TABLE_ROW.finditer(_guide_text())
    )
    assert parsed, f"no hook-table row parsed out of {_STEP_GUIDE}"
    return parsed


def _env_vars_the_tree_reads() -> dict[str, str]:
    """Find every environment variable name the source trees bind to a constant.

    A hook variable is always bound to a module constant before it reaches `os.environ`, so
    the constant assignment is the definition site an operator's name must match.

    Returns:
        (dict[str, str]) Variable name to the `path:line` that defines it.
    """
    found: dict[str, str] = {}
    for tree in _SOURCE_TREES:
        for module in sorted((_REPO_ROOT / tree).rglob("*.py")):
            parsed = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(parsed):
                if not isinstance(node, ast.Assign):
                    continue
                value = node.value
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    continue
                if not _ENV_NAME.fullmatch(value.value):
                    continue
                relative = module.relative_to(_REPO_ROOT)
                found.setdefault(value.value, f"{relative}:{node.lineno}")
    return found


def _reads_env(node: ast.AST) -> bool:
    """Whether an expression reaches the process environment.

    Args:
        node: The subtree to scan.

    Returns:
        (bool) True when it calls a `*_from_env` reader or touches `os.environ`/`os.getenv`.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "environ":
            return True
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id.endswith("_from_env"):
            return True
        if isinstance(func, ast.Attribute) and func.attr == "getenv":
            return True
    return False


def _collection_time_env_reads(test_dir: Path) -> tuple[str, ...]:
    """Find environment reads that happen while pytest collects this directory.

    Module-level statements and decorator expressions both run at import, which is when
    pytest collects. An environment read anywhere else runs after the skip decision and
    cannot change it.

    Args:
        test_dir: The test directory to scan.

    Returns:
        (tuple[str, ...]) One `file:line` per collection-time environment read.
    """
    sites: list[str] = []
    for module in sorted(test_dir.glob("*.py")):
        parsed = ast.parse(module.read_text(encoding="utf-8"))
        for statement in parsed.body:
            if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
                sites.extend(
                    f"{module.name}:{decorator.lineno}"
                    for decorator in statement.decorator_list
                    if _reads_env(decorator)
                )
                continue
            if isinstance(statement, ast.ClassDef):
                continue
            if _reads_env(statement):
                sites.append(f"{module.name}:{statement.lineno}")
    return tuple(sites)


_ROWS = _rows()
_DEFINED = _env_vars_the_tree_reads()


@pytest.mark.parametrize("row", _ROWS, ids=lambda row: row.env_var)
def test_every_documented_variable_is_read_by_the_tree(row: _Row) -> None:
    """A row naming a variable no code binds sends the operator to a hook that cannot exist."""
    assert row.env_var in _DEFINED, (
        f"{_STEP_GUIDE.name} documents {row.env_var}, which no file under "
        f"{'/, '.join(_SOURCE_TREES)}/ defines"
    )


@pytest.mark.parametrize("row", _ROWS, ids=lambda row: row.env_var)
def test_every_documented_test_path_exists(row: _Row) -> None:
    """A row pointing at a path that is not there tells the operator to run nothing."""
    assert row.test_dirs, f"{row.env_var} names no test path"
    for test_dir in row.test_dirs:
        assert (_REPO_ROOT / test_dir).is_dir(), (
            f"{_STEP_GUIDE.name} sends {row.env_var} to {test_dir}, which does not exist"
        )


def test_every_variable_the_tree_reads_is_documented() -> None:
    """The guide's table is the whole list, so an undocumented hook is a hook nobody runs."""
    documented = {row.env_var for row in _ROWS}
    undocumented = {name: site for name, site in _DEFINED.items() if name not in documented}
    assert not undocumented, (
        f"these environment variables are read by the tree but absent from the "
        f"{_STEP_GUIDE.name} hook table: {undocumented}"
    )


@pytest.mark.parametrize("row", _ROWS, ids=lambda row: row.env_var)
def test_declared_hook_status_matches_the_test_directory(row: _Row) -> None:
    """`수집시점` and `미연결` are claims about the code, so the code decides them.

    The failure this guards is the one that produced the check: a row that reads as a
    verification while the value the operator supplies changes nothing.
    """
    assert row.status in _STATUSES, (
        f"{row.env_var} declares hook status {row.status!r}; allowed: {sorted(_STATUSES)}"
    )
    if row.status not in {_STATUS_COLLECTION_TIME, _STATUS_NOT_WIRED}:
        return
    for test_dir in row.test_dirs:
        sites = _collection_time_env_reads(_REPO_ROOT / test_dir)
        if row.status == _STATUS_COLLECTION_TIME:
            assert sites, (
                f"{row.env_var} is documented {_STATUS_COLLECTION_TIME}, but nothing in "
                f"{test_dir} reads the environment while pytest collects it — setting it "
                "changes nothing and the operator would read the skip as a pass"
            )
        else:
            assert not sites, (
                f"{row.env_var} is documented {_STATUS_NOT_WIRED}, but {test_dir} does read "
                f"the environment at collection time ({', '.join(sites)}) — the hook works "
                "now and the guide is telling the operator otherwise"
            )


@pytest.mark.parametrize("guide", sorted(_GUIDE_DIR.glob("*.md")), ids=lambda guide: guide.name[:2])
def test_no_guide_names_a_live_hook_the_table_omits(guide: Path) -> None:
    """A variable named in prose but absent from the table has no status the operator can read.

    A name the tree does not read is allowed anywhere: the guide names those to tell a reader
    they do nothing. What is not allowed is a live hook mentioned outside the one table that
    says whether setting it does anything.
    """
    documented = {row.env_var for row in _ROWS}
    mentioned = set(_ENV_NAME.findall(guide.read_text(encoding="utf-8")))
    undocumented_live = {name for name in mentioned - documented if name in _DEFINED}
    assert not undocumented_live, (
        f"{guide.name} names {sorted(undocumented_live)}, which the code reads but the "
        f"{_STEP_GUIDE.name} hook table does not list"
    )


@pytest.mark.parametrize("guide", sorted(_GUIDE_DIR.glob("*.md")), ids=lambda guide: guide.name[:2])
def test_command_lines_name_documented_variables_and_real_paths(guide: Path) -> None:
    """Every `OPENARM_X=... pytest <path>` line a reader copies has to work as printed."""
    documented = {row.env_var for row in _ROWS}
    for match in _COMMAND_LINE.finditer(guide.read_text(encoding="utf-8")):
        env_var = match.group(1)
        assert env_var in documented, (
            f"{guide.name} runs {env_var}, which the {_STEP_GUIDE.name} hook table omits"
        )
        for token in match.group(2).split():
            if token.startswith("-"):
                continue
            assert (_REPO_ROOT / token).exists(), (
                f"{guide.name} tells the operator to run {token}, which does not exist"
            )
