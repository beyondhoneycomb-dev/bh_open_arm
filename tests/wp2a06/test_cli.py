"""The CLI prints the stop-path evidence and exits non-zero when a refusal fires.

The CLI is the whole of WP-2A-06's operator surface — there is no rig stage and no capture
file to hand it. These check it prints the artifact and that a refusal reaches the exit
code rather than being printed as a green-looking record.

Two of the refusals are driven through the real bench rather than a stand-in that raises.
An exception the CLI does not name still leaves a non-zero exit, so a stand-in proves only
that something went wrong; it takes the real path to show the operator is told which file
cut torque instead of being handed a traceback.
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import pytest

from backend.stopbench import cli
from backend.stopbench.bench import build_stop_path_artifact
from backend.stopbench.cli import main
from backend.stopbench.path import StopPathAnchorMissingError


def test_cli_prints_the_stop_path_artifact(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["wp_id"] == "WP-2A-06"
    assert printed["path_shape"]["stage_count"] == 4
    assert printed["no_latency_reason"]


def test_cli_takes_no_capture_argument(tmp_path: Path) -> None:
    # The old capture-file argument went with the measurement; passing one is an error
    # rather than a silently ignored path.
    with pytest.raises(SystemExit):
        main([str(tmp_path / "capture.json")])


def test_cli_exits_non_zero_when_a_refusal_fires(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse() -> dict[str, object]:
        raise StopPathAnchorMissingError("stage anchor gone")

    monkeypatch.setattr(cli, "build_stop_path_artifact", refuse)
    assert main([]) == 1
    assert "refused" in capsys.readouterr().err


def test_cli_names_the_file_that_cuts_torque(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / "cutting_stop.py").write_text(
        "def stop(bus):\n    bus.disable_torque()\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        cli,
        "build_stop_path_artifact",
        partial(build_stop_path_artifact, stop_path_root=tmp_path),
    )
    assert main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refused" in captured.err
    assert "cutting_stop.py" in captured.err


def test_cli_refuses_a_scan_that_covered_no_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(
        cli,
        "build_stop_path_artifact",
        partial(build_stop_path_artifact, stop_path_root=tmp_path / "absent"),
    )
    assert main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refused" in captured.err
    assert "parsed no file" in captured.err
