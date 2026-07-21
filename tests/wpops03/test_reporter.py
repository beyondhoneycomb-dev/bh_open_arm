"""Acceptance ③ — the runtime reporter emits the four FR-SIM-102 version fields.

Two runs: an injected-probe run for offline determinism, and a live run using the real
environment (MuJoCo and the LeRobot pin are present on this host), which is what makes
acceptance ③ an actual run rather than a fixture.
"""

from __future__ import annotations

from ops.versionpin.reporter import read_lerobot_sha, read_mujoco_version, report
from tests.wpops03.conftest import deterministic_probes


def test_report_emits_all_four_fields() -> None:
    sha, mujoco = deterministic_probes()
    versions = report(lerobot_sha_probe=lambda: sha, mujoco_probe=lambda: mujoco)
    assert versions.complete
    emitted = versions.as_dict()
    assert set(emitted) == {"lerobot_sha", "mujoco", "isaac_sim_lab", "physics_backend"}
    assert all(value.strip() for value in emitted.values())


def test_report_fields_carry_the_pinned_values() -> None:
    sha, mujoco = deterministic_probes()
    versions = report(lerobot_sha_probe=lambda: sha, mujoco_probe=lambda: mujoco)
    assert versions.lerobot_sha == sha
    assert versions.mujoco == mujoco
    assert versions.isaac_sim == "5.1.0"
    assert versions.isaac_lab == "2.3.x"
    assert versions.physics_backend == "mujoco"
    assert versions.as_dict()["isaac_sim_lab"] == "5.1.0 / 2.3.x"


def test_incomplete_report_is_flagged() -> None:
    # A silent empty field must not read as complete (never a silent gap).
    versions = report(lerobot_sha_probe=lambda: "", mujoco_probe=lambda: "3.10.0")
    assert not versions.complete


def test_live_reporter_reads_the_real_environment() -> None:
    # Acceptance ③ runs here: MuJoCo is installed and deps/lerobot.pin is committed.
    versions = report()
    assert versions.complete
    assert versions.lerobot_sha == read_lerobot_sha()
    assert len(versions.lerobot_sha) == 40  # a real commit SHA, not the unavailable marker
    assert versions.mujoco == read_mujoco_version()
    assert versions.mujoco[0].isdigit()  # a resolved version, not the unavailable marker


def test_live_lerobot_sha_matches_the_committed_pin() -> None:
    # The reporter reads WP-ENV-01's pin as data; the value must be that pin's SHA.
    versions = report()
    assert versions.lerobot_sha == "30da8e687a6dfc617fcd94afc367ac7071c376ce"
