"""Acceptance ① (socket-creation half), proven here under a real seccomp filter.

`RestrictAddressFamilies` is enforced at `socket()`, before any interface exists, so the block on
an unauthorized process can be shown on this desktop with no CAN hardware: the driver applies the
*same* directive the shipped units carry, via a transient `systemd-run --user` service, and the
probe's `socket(AF_CAN, …)` fails with `EAFNOSUPPORT`. The allow policy admits it, confirming the
filter blocks the rogue without over-blocking the authorized family.

The bus-bound remainder of ①② (an unauthorized process cannot *transmit*, the authorized writer
*does*) needs an interface to bind to and defers to `test_bus_deferred` / the reverify hook.

When no user service manager is available the seccomp filter cannot be applied, so these skip with
a reason — never assert a block that was not actually enforced.
"""

from __future__ import annotations

import errno

import pytest

from ops.acl.block_harness import (
    STAGE_CREATE_BLOCKED,
    AttemptOutcome,
    attempt_can_socket,
    run_attempt_under_families,
    user_manager_available,
)
from ops.acl.policy import AUTHORIZED_FAMILIES, CAN_FAMILY

_ALLOW_POLICY = " ".join(AUTHORIZED_FAMILIES)
_DENY_POLICY = f"~{CAN_FAMILY}"

pytestmark = pytest.mark.skipif(
    not user_manager_available(),
    reason="no user service manager (systemd-run --user); seccomp filter cannot be applied here",
)


def _create_only(policy: str) -> AttemptOutcome:
    """Run the probe under a family policy, attempting socket creation only (no bus).

    Args:
        policy: The `RestrictAddressFamilies=` value to apply.

    Returns:
        (AttemptOutcome) The probe's outcome under that policy.
    """
    return run_attempt_under_families(policy, interface=None, do_bind=False, do_send=False)


def test_unsandboxed_process_can_open_the_bus_socket() -> None:
    """The rogue baseline: with no sandbox, AF_CAN socket creation just succeeds.

    This is why the mandatory layer must exist — the cooperative flock cannot stop this, so the
    block below is not redundant with WP-0B-01.
    """
    outcome = attempt_can_socket(interface=None, do_bind=False, do_send=False)
    assert outcome.created is True


def test_deny_policy_blocks_can_socket_creation() -> None:
    """Acceptance ①: under `~AF_CAN`, the unauthorized probe cannot even create the socket."""
    outcome = _create_only(_DENY_POLICY)
    assert outcome.created is False
    assert outcome.stage == STAGE_CREATE_BLOCKED
    assert outcome.errno == errno.EAFNOSUPPORT


def test_allow_policy_admits_can_socket_creation() -> None:
    """The authorized family set is not over-blocked: AF_CAN socket creation succeeds."""
    outcome = _create_only(_ALLOW_POLICY)
    assert outcome.created is True
    assert outcome.errno is None
