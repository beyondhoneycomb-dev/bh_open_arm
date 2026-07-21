"""WP-ENV-02 acceptance ④ — the committed lockfile exists and pins the SHA-pinned LeRobot."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / "uv.lock"
PIN_SHA = "30da8e687a6dfc617fcd94afc367ac7071c376ce"


def test_lockfile_exists_and_is_nonempty() -> None:
    assert LOCK_PATH.is_file()
    assert LOCK_PATH.stat().st_size > 0


def test_lockfile_pins_lerobot_by_commit_sha() -> None:
    # The universal lock resolves the [robot] group; LeRobot is a git dependency
    # pinned to the same SHA as deps/lerobot.pin — a bare semver would not appear.
    text = LOCK_PATH.read_text(encoding="utf-8")
    assert PIN_SHA in text


def test_host_freeze_is_recorded() -> None:
    freeze = REPO_ROOT / "targets" / "host-rtx5080.freeze.txt"
    assert freeze.is_file()
    assert "lerobot==0.6.0" in freeze.read_text(encoding="utf-8")
