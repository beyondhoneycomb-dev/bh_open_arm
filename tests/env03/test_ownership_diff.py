"""WP-ENV-03 acceptance ⑥ — the ownership-diff gate rejects intrusion, not own edits."""

from __future__ import annotations

from pathlib import Path

import ownership_diff

REPO_ROOT = Path(__file__).resolve().parents[2]

# A minimal three-owner map; the real registry map is exercised separately below.
OWNERSHIP = {
    "WP-ENV-03": (".github/**",),
    "WP-BOOT-03": ("registry/checks/**", "registry/check.py"),
    "WP-ENV-01": ("deps/**",),
}


def test_intrusion_into_another_exclusive_tree_is_blocked() -> None:
    verdict = ownership_diff.check_diff(
        "WP-ENV-03",
        (".github/workflows/env.yml", "registry/checks/ci_99.py"),
        OWNERSHIP,
    )
    assert verdict.blocked
    assert any("WP-BOOT-03" in reason for _, reason in verdict.violations)


def test_own_tree_only_is_not_over_blocked() -> None:
    verdict = ownership_diff.check_diff(
        "WP-ENV-03",
        (".github/workflows/env.yml", ".github/ownership_diff.py"),
        OWNERSHIP,
    )
    assert not verdict.blocked


def test_unowned_non_furniture_path_is_blocked() -> None:
    verdict = ownership_diff.check_diff("WP-ENV-01", ("backend/actuation/x.py",), OWNERSHIP)
    assert verdict.blocked


def test_furniture_is_allowed() -> None:
    verdict = ownership_diff.check_diff("WP-ENV-01", ("README.md", "docs/spec/01.md"), OWNERSHIP)
    assert not verdict.blocked


def test_real_registry_ownership_covers_the_env_packages() -> None:
    ownership = ownership_diff.load_ownership(REPO_ROOT / "registry" / "traceability.yaml")
    for wp in ("WP-ENV-01", "WP-ENV-02", "WP-ENV-03", "WP-ENV-04"):
        assert wp in ownership, f"{wp} declares no EXCLUSIVE ownership"
    # A real intrusion against the committed map is blocked.
    verdict = ownership_diff.check_diff("WP-ENV-04", ("registry/checks/ci_99.py",), ownership)
    assert verdict.blocked
