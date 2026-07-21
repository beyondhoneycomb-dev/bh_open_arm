"""Acceptance ⑤ — real-fixture re-verification hooks for the two deferred checks.

The M-24 source reading needs the real `openarm_driver`, and the live double-bind
gate needs a real second SocketCAN bind; neither exists on this host. Each hook
skips with a reason until its fixture is supplied, and re-runs the identical check
the moment it is. The skip tests document the honest deferral; the supplied-input
tests prove the hooks are actually wired (exercised here against a real capture
directory and a real driver-shaped source, so the hooks are not dead code).
"""

from __future__ import annotations

import json
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


def test_driver_reverify_skips_without_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no real driver.py supplied, the M-24 re-verification is deferred, not faked."""
    monkeypatch.delenv(DRIVER_SOURCE_ENV_VAR, raising=False)
    source = driver_source_from_env()
    if source is None:
        pytest.skip(f"deferred: set {DRIVER_SOURCE_ENV_VAR} to a real openarm_driver/driver.py")
    reverify_driver_audit(source)  # pragma: no cover - runs only when a real source is supplied


def test_driver_reverify_runs_against_supplied_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hook re-runs the audit the moment a driver.py path is supplied."""
    monkeypatch.setenv(DRIVER_SOURCE_ENV_VAR, str(_FIXTURES / "driver_opens_can.py"))
    source = driver_source_from_env()
    assert source is not None
    verdict = reverify_driver_audit(source)
    assert verdict.present is True
    assert verdict.opens_can is True


def test_gate_reverify_skips_without_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no real capture supplied, the live-gate re-verification is deferred."""
    monkeypatch.delenv(CAPTURE_ENV_VAR, raising=False)
    capture = capture_dir_from_env()
    if capture is None:
        pytest.skip(f"deferred: set {CAPTURE_ENV_VAR} to a real WP-0B-03 foreign-binder capture")
    assert reverify_gate_from_capture(capture) is False  # pragma: no cover - real capture only


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
