"""WP-3D-07 ②: the `openarm-dataset-convert`-shaped CLI enforces the policy end to end.

A v3.0 legacy import exits zero; a `gr00t`/`lerobot_v2.1` output and a LeRobot input
exit non-zero with the refusal on stderr. This is the runtime half of "0 export path"
exercised through the same entry an operator would call.
"""

from __future__ import annotations

import pytest

from backend.dataset.import_export.cli import EXIT_OK, EXIT_REFUSED, main


def test_v30_import_exits_ok(capsys: pytest.CaptureFixture[str]) -> None:
    """A legacy OpenArm -> v3.0 import is authorized (exit 0) and reports the isolated env."""
    code = main(
        ["/data/legacy", "/data/out", "--format", "lerobot_v3.0", "--input-kind", "legacy_openarm"]
    )
    assert code == EXIT_OK
    assert "isolated env" in capsys.readouterr().out


@pytest.mark.parametrize("output_format", ["gr00t", "lerobot_v2.1"])
def test_blocked_export_exits_refused(
    output_format: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A gr00t / v2.1 output is refused with a non-zero exit (`FR-DAT-042`)."""
    code = main(["/data/legacy", "/data/out", "--format", output_format])
    assert code == EXIT_REFUSED
    assert "refused" in capsys.readouterr().err


def test_lerobot_input_exits_refused(capsys: pytest.CaptureFixture[str]) -> None:
    """A LeRobot input (an export of our own data) is refused (`FR-DAT-039`)."""
    code = main(
        ["/data/native", "/data/out", "--format", "lerobot_v3.0", "--input-kind", "lerobot"]
    )
    assert code == EXIT_REFUSED
    assert "no LeRobot-input path" in capsys.readouterr().err
