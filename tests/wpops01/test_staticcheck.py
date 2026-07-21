"""Static acceptance ④ (sandbox present and sound) and the ③ tie-in (flock kept alive).

The shipped units must pass every check; each check must also reject the specific corruption it
exists to catch, or it is a green that catches nothing. The negative cases below are that proof.
"""

from __future__ import annotations

from pathlib import Path

from ops.acl.policy import REQUIRED_DIRECTIVES, WRITER_UNIT_FILENAME
from ops.acl.staticcheck import (
    find_dropin_not_denying_can,
    find_lock_dir_not_writable,
    find_missing_sandbox_directives,
)

_UNITS = Path(__file__).resolve().parents[2] / "ops" / "acl" / "units"


def _writer_text() -> str:
    """Return the shipped writer unit body."""
    return (_UNITS / WRITER_UNIT_FILENAME).read_text(encoding="utf-8")


def _deny_dropin_text() -> str:
    """Return the shipped deny drop-in body."""
    return (_UNITS / "10-openarm-deny-can.conf").read_text(encoding="utf-8")


def test_shipped_writer_unit_passes_every_directive_check() -> None:
    """Acceptance ④: the shipped writer unit carries every required, sound sandbox directive."""
    assert find_missing_sandbox_directives(_writer_text()) == []


def test_shipped_writer_unit_keeps_flock_alive() -> None:
    """Acceptance ③: the shipped writer re-grants the lock directory under a sealed filesystem."""
    assert find_lock_dir_not_writable(_writer_text()) == []


def test_shipped_deny_dropin_denies_can() -> None:
    """The shipped drop-in actually denies AF_CAN to non-writer units."""
    assert find_dropin_not_denying_can(_deny_dropin_text()) == []


def test_stripped_unit_flags_every_missing_directive() -> None:
    """A unit with no sandbox directives is flagged once per required directive."""
    violations = find_missing_sandbox_directives("[Service]\nExecStart=/bin/true\n")
    flagged = {v.key for v in violations}
    assert flagged == {d.key for d in REQUIRED_DIRECTIVES}


def test_open_device_policy_is_rejected() -> None:
    """A device ACL that is not `closed` is rejected (the device-ACL half of ④)."""
    text = _writer_text().replace("DevicePolicy=closed", "DevicePolicy=auto")
    violations = find_missing_sandbox_directives(text)
    assert any(v.key == "DevicePolicy" for v in violations)


def test_allowlist_leaking_ip_family_is_rejected() -> None:
    """Admitting an IP family widens the sandbox past what a CAN writer needs — rejected."""
    text = _writer_text().replace(
        "RestrictAddressFamilies=AF_CAN AF_NETLINK AF_UNIX",
        "RestrictAddressFamilies=AF_CAN AF_NETLINK AF_UNIX AF_INET",
    )
    violations = find_missing_sandbox_directives(text)
    assert any("AF_INET" in v.reason for v in violations)


def test_allowlist_without_can_is_rejected() -> None:
    """An allowlist that omits AF_CAN would over-block the authorized writer — rejected."""
    text = _writer_text().replace(
        "RestrictAddressFamilies=AF_CAN AF_NETLINK AF_UNIX",
        "RestrictAddressFamilies=AF_NETLINK AF_UNIX",
    )
    violations = find_missing_sandbox_directives(text)
    assert any("does not admit AF_CAN" in v.reason for v in violations)


def test_writer_using_deny_form_is_rejected() -> None:
    """A writer unit must express an allowlist, not an inverted deny form."""
    text = _writer_text().replace(
        "RestrictAddressFamilies=AF_CAN AF_NETLINK AF_UNIX",
        "RestrictAddressFamilies=~AF_INET AF_INET6",
    )
    violations = find_missing_sandbox_directives(text)
    assert any("inverted (deny) form" in v.reason for v in violations)


def test_sealed_filesystem_without_lock_grant_is_rejected() -> None:
    """Acceptance ③ negative: sealing the filesystem without re-granting /run/lock is rejected."""
    text = _writer_text().replace("ReadWritePaths=/run/lock", "")
    violations = find_lock_dir_not_writable(text)
    assert len(violations) == 1
    assert "/run/lock" in violations[0].reason


def test_lock_grant_unneeded_when_filesystem_not_sealed() -> None:
    """With no ProtectSystem seal there is nothing to re-grant, so the check is silent."""
    text = "[Service]\nUser=openarm\nExecStart=/bin/true\n"
    assert find_lock_dir_not_writable(text) == []


def test_dropin_that_allows_can_is_caught() -> None:
    """A drop-in that names the directive but forgets the ~ inversion would ALLOW CAN — caught."""
    violations = find_dropin_not_denying_can("[Service]\nRestrictAddressFamilies=AF_CAN\n")
    assert len(violations) == 1
    assert "ALLOWS AF_CAN" in violations[0].reason


def test_dropin_silent_on_can_is_caught() -> None:
    """A drop-in that never mentions AF_CAN does not deny it — caught."""
    violations = find_dropin_not_denying_can("[Service]\nRestrictAddressFamilies=~AF_INET\n")
    assert len(violations) == 1
    assert "does not deny AF_CAN" in violations[0].reason
