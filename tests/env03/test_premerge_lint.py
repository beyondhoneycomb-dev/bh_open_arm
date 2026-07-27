"""WP-ENV-03 acceptance ③ ④ — push_to_hub and plugin-naming violation fixtures fail."""

from __future__ import annotations

import re
import tomllib

import premerge_lint

from registry import REPO_ROOT

PYPROJECT = REPO_ROOT / "pyproject.toml"
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"

_PYPROJECT_RUFF = re.compile(r"^ruff==(?P<version>[0-9.]+)$")
_PRE_COMMIT_RUFF_REV = re.compile(
    r"repo:\s*https://github\.com/astral-sh/ruff-pre-commit.*?^\s*rev:\s*v(?P<version>[0-9.]+)",
    re.DOTALL | re.MULTILINE,
)


def _pinned_ruff_version() -> str:
    """The exact ruff version pyproject's dev group installs.

    Returns:
        (str) The pinned version.

    Raises:
        AssertionError: When the dev group carries no exact `ruff==` pin. A range
            lets CI resolve a newer formatter than the hook that formatted the tree.
    """
    dev = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["optional-dependencies"][
        "dev"
    ]
    pins = [m.group("version") for m in (_PYPROJECT_RUFF.match(spec) for spec in dev) if m]
    assert pins, f"pyproject [dev] carries no exact ruff== pin; got {dev}"
    return pins[0]


def test_ruff_is_pinned_identically_for_the_hook_and_the_gate() -> None:
    """The formatter that writes and the formatter that judges must be one version.

    `ruff format` output changes between releases. The pre-commit hook formats the
    tree and CI's `ruff format --check` judges it, so two versions means a commit
    the hook just formatted is rejected by the gate — and neither file records the
    disagreement, so the failure reads as a formatting mistake rather than a pin.
    """
    hook = _PRE_COMMIT_RUFF_REV.search(PRE_COMMIT.read_text(encoding="utf-8"))
    assert hook is not None, ".pre-commit-config.yaml declares no ruff-pre-commit rev"
    assert hook.group("version") == _pinned_ruff_version(), (
        f"pre-commit pins ruff v{hook.group('version')} but pyproject [dev] pins "
        f"{_pinned_ruff_version()}; the hook's formatting would fail CI's check"
    )


def test_push_to_hub_true_without_opt_in_is_rejected() -> None:
    result = premerge_lint.check_push_to_hub({"push_to_hub": True})
    assert not result.ok


def test_push_to_hub_true_with_audited_opt_in_is_allowed() -> None:
    result = premerge_lint.check_push_to_hub(
        {"push_to_hub": True, "push_to_hub_opt_in_audited": True}
    )
    assert result.ok


def test_push_to_hub_default_false_is_allowed() -> None:
    assert premerge_lint.check_push_to_hub({}).ok


def test_reserved_plugin_prefixes_are_allowed() -> None:
    for name in ("lerobot_robot_openarm", "lerobot_teleoperator_quest", "lerobot_camera_realsense"):
        assert premerge_lint.check_plugin_name(name).ok


def test_off_convention_plugin_name_is_rejected() -> None:
    for name in ("openarm_follower", "lerobot_plugin_openarm", "robot_openarm"):
        assert not premerge_lint.check_plugin_name(name).ok
