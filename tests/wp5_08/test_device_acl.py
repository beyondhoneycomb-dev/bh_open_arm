"""CG-5-08h — ACL/sandbox static config runs; the live cansend-TX-fail check defers.

The device-ACL/systemd-sandbox config and its harness are the reused `ops.acl`
(`WP-OPS-01`). Its static soundness runs here: the shipped writer unit carries every
sandbox directive with sound values and the deny drop-in actually denies AF_CAN. The
live half — proving an unauthorised `cansend` cannot transmit — needs a CAN interface
this host does not have, so it is deferred with a re-verification hook and never faked
green (the ONE RULE).
"""

from __future__ import annotations

import pytest

from backend.security.device_acl import (
    live_can_tx_status,
    reverify_live_can_tx,
    static_config_report,
)


def test_shipped_acl_sandbox_config_is_statically_sound() -> None:
    report = static_config_report()
    assert report.violations == (), f"ACL/sandbox static defects: {report.violations}"
    assert report.sound is True
    assert report.writer_unit.is_file()
    assert report.deny_dropin.is_file()


def test_live_can_tx_deferred_without_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    # No vcan/CAN interface on this dev host: the ACL vcan env var is unset.
    monkeypatch.delenv("OPENARM_ACL_VCAN_INTERFACE", raising=False)
    status = live_can_tx_status()

    assert status.deferred is True
    assert status.interface is None
    assert "deferred" in status.reason.lower()


def test_live_reverify_hook_refuses_to_fake_a_green(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENARM_ACL_VCAN_INTERFACE", raising=False)
    with pytest.raises(RuntimeError):
        reverify_live_can_tx()
