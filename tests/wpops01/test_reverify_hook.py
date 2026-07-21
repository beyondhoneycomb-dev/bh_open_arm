"""The bus re-verification hook (plan 02a §4.1): its contract logic runs here; the live path defers.

Two things are proven. First, that the hook *logic* is a real check and not a rubber stamp — it is
run against synthetic captures and must pass a consistent one while catching both an unauthorized
leak and an authorized over-block. Second, that the true bus path stays honest: it skips with a
reason until a vcan interface is named, and re-runs the identical live check the moment one is.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ops.acl.block_harness import (
    STAGE_BIND_FAILED,
    STAGE_CREATE_BLOCKED,
    STAGE_CREATED,
    STAGE_SENT,
    AttemptOutcome,
)
from ops.acl.reverify import (
    VCAN_ENV_VAR,
    reverify_from_capture,
    reverify_on_interface,
    vcan_interface_from_env,
)

_BLOCKED = AttemptOutcome(False, False, False, STAGE_CREATE_BLOCKED, 97, "blocked")
_SENT = AttemptOutcome(True, True, True, STAGE_SENT, None, None)
_LEAKED = AttemptOutcome(True, False, False, STAGE_CREATED, None, None)
_OVER_BLOCKED = AttemptOutcome(True, False, False, STAGE_BIND_FAILED, 1, "over-blocked")


def _write_capture(path: Path, deny: AttemptOutcome, allow: AttemptOutcome) -> Path:
    """Write a deny/allow capture in the shape the hook consumes.

    Args:
        path: Destination file.
        deny: The outcome recorded for the unauthorized (deny-policy) probe.
        allow: The outcome recorded for the authorized (allow-policy) probe.

    Returns:
        (Path) The written path.
    """
    path.write_text(
        json.dumps({"deny": deny.as_dict(), "allow": allow.as_dict()}), encoding="utf-8"
    )
    return path


def test_consistent_capture_matches(tmp_path: Path) -> None:
    """A capture where the rogue was blocked and the writer transmitted verifies."""
    capture = _write_capture(tmp_path / "ok.json", deny=_BLOCKED, allow=_SENT)
    report = reverify_from_capture(capture)
    assert report.matched is True
    assert set(report.checked) == {"unauthorized_blocked", "authorized_transmits"}
    assert report.mismatches == ()


def test_unauthorized_leak_is_caught(tmp_path: Path) -> None:
    """A capture where the unauthorized probe was NOT blocked is rejected."""
    capture = _write_capture(tmp_path / "leak.json", deny=_LEAKED, allow=_SENT)
    report = reverify_from_capture(capture)
    assert report.matched is False
    assert any("not blocked" in m for m in report.mismatches)


def test_authorized_over_block_is_caught(tmp_path: Path) -> None:
    """A capture where the authorized writer failed to transmit is rejected (over-block)."""
    capture = _write_capture(tmp_path / "overblock.json", deny=_BLOCKED, allow=_OVER_BLOCKED)
    report = reverify_from_capture(capture)
    assert report.matched is False
    assert any("did not transmit" in m for m in report.mismatches)


@pytest.mark.skipif(
    VCAN_ENV_VAR not in os.environ,
    reason=f"set {VCAN_ENV_VAR} to a real vcan interface to re-verify the block live",
)
def test_reverify_against_real_bus() -> None:
    """Deferred live path: re-run the block acceptance against a real vcan interface."""
    interface = vcan_interface_from_env()
    assert interface is not None
    report = reverify_on_interface(interface)
    assert report.matched, f"live bus re-verification failed: {report.mismatches}"
