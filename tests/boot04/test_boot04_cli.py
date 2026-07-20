"""The CLI surface: every predicate the suite asserts must also hold from a shell.

Rejections have to exit non-zero. A command that prints a complaint and exits 0 is invisible to
CI, which makes the rule it was enforcing unenforced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ops.launch.cli import EXIT_OK, EXIT_REJECTED, main

EVIDENCE = "sha256:" + "e" * 64
TRIGGER = "PG-SAFE-001:FAIL_BLOCKING"


def test_transition_command_commits_and_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "--state-dir",
            str(tmp_path),
            "transition",
            "WP-BOOT-04",
            "--to",
            "active",
            "--trigger",
            "spawn",
            "--evidence-hash",
            EVIDENCE,
        ]
    )
    assert code == EXIT_OK
    assert '"new_state": "active"' in capsys.readouterr().out


def test_illegal_transition_exits_non_zero(tmp_path: Path) -> None:
    """A rejected transition must be visible to CI as a failure."""
    main(
        [
            "--state-dir",
            str(tmp_path),
            "transition",
            "WP-BOOT-04",
            "--to",
            "active",
            "--trigger",
            "spawn",
            "--evidence-hash",
            EVIDENCE,
        ]
    )
    code = main(
        [
            "--state-dir",
            str(tmp_path),
            "transition",
            "WP-BOOT-04",
            "--to",
            "active",
            "--trigger",
            "again",
            "--evidence-hash",
            EVIDENCE,
        ]
    )
    assert code == EXIT_REJECTED


def test_transitions_command_prints_the_table(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["transitions"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "not_started -> active" in output
    assert "integrated -> cancelled" not in output


def test_closure_command_reports_depth(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    registry = tmp_path / "reg.yaml"
    registry.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "spine_ref": "test",
                "entries": [
                    {
                        "req": "PLAN-BOOT-01",
                        "wp": "WP-A-01",
                        "stale_on": [TRIGGER],
                        "downstream": ["WP-B-01"],
                        "artifact": [],
                    },
                    {
                        "req": "PLAN-BOOT-02",
                        "wp": "WP-B-01",
                        "stale_on": [],
                        "downstream": [],
                        "artifact": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert main(["closure", TRIGGER, "--registry", str(registry)]) == EXIT_OK
    output = capsys.readouterr().out
    assert "WP-A-01" in output
    assert "WP-B-01" in output


def test_shape_command_reports_resolved_fanout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "m.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "wp_id": "WP-3B-01",
                "workflow": "SHAPE-IM",
                "exec_class": "AI-offline",
                "owns": [
                    {"glob": "a/**", "mode": "EXCLUSIVE"},
                    {"glob": "b/**", "mode": "EXCLUSIVE"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert main(["shape", str(manifest)]) == EXIT_OK
    assert "n=2" in capsys.readouterr().out


def test_shape_command_rejects_a_bad_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "bad.yaml"
    manifest.write_text(
        yaml.safe_dump({"wp_id": "WP-0B-06", "workflow": "SHAPE-MS(3)", "exec_class": "AI-on-HW"}),
        encoding="utf-8",
    )
    assert main(["shape", str(manifest)]) == EXIT_REJECTED


def test_check_latch_command_passes_on_the_production_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    assert main(["check-latch", "--root", str(repo_root / "ops")]) == EXIT_OK
    assert "0 external latch call sites" in capsys.readouterr().out


def test_check_latch_command_fails_on_the_violation_corpus() -> None:
    fixtures = Path(__file__).resolve().parent / "fixtures"
    assert main(["check-latch", "--root", str(fixtures)]) == EXIT_REJECTED
