"""Acceptance ⑤ — real-fixture re-verification hooks for the two deferred checks.

The M-24 source reading needs the real `openarm_driver`, and the live double-bind
gate needs a real second SocketCAN bind; neither exists on a desktop. Offline each
one skips with a reason. Both read the operator's environment at collection, so
naming a real `driver.py` or a real capture directory runs the deferred check over
those bytes and it can fail. The supplied-input tests point the same hooks at a
driver-shaped source and a capture this repository ships, so neither is dead code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.can.bind.reverify import (
    CAPTURE_ENV_VAR,
    CAPTURE_FILENAME,
    DRIVER_SOURCE_ENV_VAR,
    capture_dir_from_env,
    driver_source_from_env,
    reverify_driver_audit,
    reverify_gate_from_capture,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Read once, at collection: the operator names both on the pytest command line, so the skip
# decisions and the assertions below must see the same values. The skips turn on the raw
# strings rather than the resolved paths — a mistyped path is a typo to report, not a deferral
# to honour, and resolving first would silently turn it back into a skip.
_DRIVER_SOURCE_ENV_RAW = os.environ.get(DRIVER_SOURCE_ENV_VAR, "")
_CAPTURE_ENV_RAW = os.environ.get(CAPTURE_ENV_VAR, "")


@pytest.mark.skipif(
    not _DRIVER_SOURCE_ENV_RAW,
    reason=(
        f"the M-24 source reading needs the real openarm_driver, absent here; set "
        f"{DRIVER_SOURCE_ENV_VAR} to a real openarm_driver/driver.py to run it"
    ),
)
def test_driver_reverify_runs_against_the_real_driver_source() -> None:
    """The M-24 audit over the operator's real driver.py, judged by its citations.

    `M-24` is open in the spec, so neither answer to "does it open CAN" can be asserted here.
    What can be asserted is that the verdict is usable: `present` is set unconditionally by
    `audit_driver_source`, so reading it asks nothing — and `opens_can` is only actionable if
    the operator can go to the cited line and see the construct. So the citations are checked
    against the file they name.
    """
    source = driver_source_from_env()
    assert source is not None, (
        f"{DRIVER_SOURCE_ENV_VAR} names {_DRIVER_SOURCE_ENV_RAW!r}, which is not a file"
    )
    verdict = reverify_driver_audit(source)
    assert verdict.source_path == str(source), (
        f"the verdict cites {verdict.source_path} but the operator named {source}"
    )
    assert verdict.opens_can is not None, f"{source} left M-24 unsettled"
    assert bool(verdict.cited_lines) is verdict.opens_can, (
        f"opens_can={verdict.opens_can} with {len(verdict.cited_lines)} cited lines"
    )

    lines = source.read_text(encoding="utf-8").splitlines()
    for cited in verdict.cited_lines:
        assert 1 <= cited.line <= len(lines), f"{source}:{cited.line} is outside the file"
        assert cited.text == lines[cited.line - 1].strip(), (
            f"{source}:{cited.line} cites {cited.text!r} but holds "
            f"{lines[cited.line - 1].strip()!r}"
        )


def test_driver_reverify_runs_against_supplied_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hook re-runs the audit the moment a driver.py path is supplied."""
    monkeypatch.setenv(DRIVER_SOURCE_ENV_VAR, str(_FIXTURES / "driver_opens_can.py"))
    source = driver_source_from_env()
    assert source is not None
    verdict = reverify_driver_audit(source)
    assert verdict.present is True
    assert verdict.opens_can is True


@pytest.mark.skipif(
    not _CAPTURE_ENV_RAW,
    reason=(
        f"the live double-bind gate needs a real second SocketCAN binder, absent here; set "
        f"{CAPTURE_ENV_VAR} to a real WP-0B-03 foreign-binder capture directory to run it"
    ),
)
def test_gate_reverify_refuses_connect_on_the_real_capture() -> None:
    """A real rig's captured foreign binder, replayed through the gate, still refuses connect."""
    capture_dir = capture_dir_from_env()
    assert capture_dir is not None, (
        f"{CAPTURE_ENV_VAR} names {_CAPTURE_ENV_RAW!r}, which is not a directory"
    )
    assert reverify_gate_from_capture(capture_dir) is False


def test_gate_reverify_refuses_connect_on_supplied_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The hook replays a captured binder through the gate, which refuses to connect."""
    capture = [{"iface": "can0", "detail": "captured second writer", "holder_pid": 9001}]
    (tmp_path / CAPTURE_FILENAME).write_text(json.dumps(capture), encoding="utf-8")
    monkeypatch.setenv(CAPTURE_ENV_VAR, str(tmp_path))
    resolved = capture_dir_from_env()
    assert resolved is not None
    assert reverify_gate_from_capture(resolved) is False
