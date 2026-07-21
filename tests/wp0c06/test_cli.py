"""The CLI runs the harness unattended and writes (or honestly refuses) the artifact.

One `--quick` invocation exercises the whole pipeline end to end and writes a valid
artifact JSON, exiting 0; this is the command a caller runs to produce a PG-RT-001a
basis artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim.harness.cli import main


def test_cli_writes_a_valid_artifact(tmp_path: Path) -> None:
    """A quick CLI run writes a well-formed artifact and exits 0."""
    out = tmp_path / "artifact.json"
    code = main(
        [
            "--out",
            str(out),
            "--quick",
            "--streams",
            "3",
            "--width",
            "160",
            "--height",
            "120",
            "--png-bytes",
            "8192",
            "--serialize-bytes",
            "16384",
        ]
    )
    assert code == 0
    assert out.exists()
    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert artifact["wp_id"] == "WP-0C-06"
    assert artifact["connect_call_count"] == 0
    assert artifact["load_profile"]["stream_count"] == 3
    assert len(artifact["conditions"]) == 7


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
