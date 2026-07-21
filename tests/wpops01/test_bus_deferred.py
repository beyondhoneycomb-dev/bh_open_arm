"""Acceptance ①②, bus-bound half — deferred to vcan, skipped-with-reason, never faked.

Proving that an unauthorized process cannot *transmit* (not merely cannot create a socket) and that
the authorized writer *does* transmit with zero over-block needs an interface to bind to. This host
has none. So this runs only when a vcan interface is named via `OPENARM_ACL_VCAN_INTERFACE`, and
otherwise skips with the reason and a pointer to the re-verification hook (plan 02a §4.1) that
carries the identical check to a rig.
"""

from __future__ import annotations

import pytest

from ops.acl.block_harness import user_manager_available
from ops.acl.reverify import VCAN_ENV_VAR, reverify_on_interface, vcan_interface_from_env

_INTERFACE = vcan_interface_from_env()

_NO_BUS_REASON = (
    f"no CAN bus on this host: set {VCAN_ENV_VAR} to a vcan interface (e.g. vcan0) on a rig to "
    "verify that the deny policy blocks transmit and the allow policy transmits. The identical "
    "check runs via ops.acl.reverify.reverify_on_interface."
)


@pytest.mark.skipif(_INTERFACE is None, reason=_NO_BUS_REASON)
@pytest.mark.skipif(
    not user_manager_available(),
    reason="no user service manager to apply the RestrictAddressFamilies sandbox",
)
def test_block_and_pass_through_on_a_real_bus() -> None:
    """Deferred ①②: unauthorized transmit blocked, authorized transmit succeeds (0 over-block)."""
    assert _INTERFACE is not None  # narrowed by the skipif; restated for the type checker
    report = reverify_on_interface(_INTERFACE)
    assert report.matched, f"bus-bound acceptance failed: {report.mismatches}"
