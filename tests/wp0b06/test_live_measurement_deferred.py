"""Deferred: the live M-1 measurement needs the sweep tool and a locatable adapter.

Real RTT / f_max_can / frames-per-cycle / USB-2.0 link-speed measurement cannot run
without a `motor_sampling_check` binary and a CAN adapter `parse_topology` can find,
so this skips with a reason rather than asserting a fabricated green. The availability
probe is the same one the orchestrator uses, so the skip is driven by the real
condition, not a hardcoded flag.

The probe is an AND of two independent halves, and it reports only their conjunction.
A host that has the adapter physically attached but bound to a driver other than
`CAN_ADAPTER_DRIVER` fails the topology half while looking, from the outside, exactly
like a host with no adapter at all. The re-verification hook in `test_reverify_hook.py`
is what distinguishes them: it runs the identical parse chain against a real capture
and says what the tree actually contained.
"""

from __future__ import annotations

import pytest

from ops.hw.usb.measure import real_measurement_available
from ops.hw.usb.topology import CAN_ADAPTER_DRIVER


def test_real_measurement_unavailable_here() -> None:
    """The live path refuses to run here, so no accidental run can fabricate an artifact.

    A positive assertion about the environment rather than a skip: it documents that the
    deferral is real and that the probe fails closed. It says nothing about *which* half is
    missing, and it cannot — that is the reverify hook's job against a real capture.
    """
    assert real_measurement_available() is False


@pytest.mark.skipif(
    not real_measurement_available(),
    reason=(
        "deferred: real RTT/f_max_can/frames-per-cycle/USB-2.0 link-speed measurement needs "
        "the motor_sampling_check tool (set OPENARM_MSC_BIN) and an adapter that `lsusb -t` "
        f"reports bound to {CAN_ADAPTER_DRIVER}; the probe reports the pair unsatisfied here. "
        "An attached adapter bound to some other driver leaves this skipping, so read the "
        "probe's two halves before concluding which one is missing"
    ),
)
def test_live_measurement_runs_on_rig() -> None:
    """On the rig this would run the full sweep and publish a hardware artifact."""
    # Intentionally unreachable on this host; present so the acceptance runs the
    # instant a rig with an adapter and the tool is available.
    pytest.fail("real_measurement_available() returned True but no rig wiring in test env")
