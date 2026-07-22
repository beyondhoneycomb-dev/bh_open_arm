"""The offline CLI: assembles the decomposition for a capture, refuses an untrusted one.

The CLI is the on-host entry point for the parts of WP-2C-06 that run without a rig. These
check it prints an artifact for a trusted capture and exits non-zero — rather than printing a
green-looking artifact — when the capture's clock cannot be trusted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.reaction_bench.cli import main
from backend.torque_bringup.constants import (
    CLOCK_METHOD_CANDUMP_HW_TIMESTAMP,
    CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING,
)


def _write_capture(path: Path, method: str) -> None:
    """Write a one-sample capture with the given clock method to `path`.

    Args:
        path: File to write.
        method: Clock-provenance method to declare.
    """
    capture = {
        "host_id": "cli-host",
        "clock_provenance": {"method": method, "offset_sec": 1e-6, "uncertainty_sec": 1e-7},
        "samples": [
            {
                "detection_confirm_at": 0.0,
                "reaction_select_at": 0.002,
                "scheduler_write_at": 0.005,
                "can_first_byte_at": 0.009,
            }
        ],
    }
    path.write_text(json.dumps(capture), encoding="utf-8")


def test_cli_prints_artifact_for_a_trusted_capture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capture = tmp_path / "capture.json"
    _write_capture(capture, CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING)
    assert main([str(capture)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["wp_id"] == "WP-2C-06"
    assert printed["reaction_time"]["sample_count"] == 1


def test_cli_refuses_a_candump_forge_capture(tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    _write_capture(capture, CLOCK_METHOD_CANDUMP_HW_TIMESTAMP)
    assert main([str(capture)]) == 1
