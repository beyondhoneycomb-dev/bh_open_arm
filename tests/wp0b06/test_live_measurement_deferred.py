"""Deferred: the live M-1 measurement needs a real adapter and the sweep tool.

Real RTT / f_max_can / frames-per-cycle / USB-2.0 link-speed measurement cannot run
on a host with no CAN adapter and no `motor_sampling_check` binary, so this skips
with a reason rather than asserting a fabricated green. The availability probe is
the same one the orchestrator uses, so the skip is driven by the real condition,
not a hardcoded flag. The re-verification hook in `test_reverify_hook.py` is the
mechanism that runs the identical parse chain against real captures once supplied.
"""

from __future__ import annotations

import pytest

from ops.hw.usb.measure import real_measurement_available


def test_real_measurement_unavailable_here() -> None:
    """This host has no adapter/tool, so the live path correctly refuses to run.

    This is a positive assertion about the environment, not a skip: it documents
    that the deferral is real (the probe fails closed), which is what keeps a later
    accidental live run on this desktop from silently producing a fake artifact.
    """
    assert real_measurement_available() is False


@pytest.mark.skipif(
    not real_measurement_available(),
    reason=(
        "deferred: real RTT/f_max_can/frames-per-cycle/USB-2.0 link-speed measurement "
        "needs a real CAN adapter and the motor_sampling_check tool (set OPENARM_MSC_BIN); "
        "neither exists on this host — re-run once on the rig"
    ),
)
def test_live_measurement_runs_on_rig() -> None:
    """On the rig this would run the full sweep and publish a hardware artifact."""
    # Intentionally unreachable on this host; present so the acceptance runs the
    # instant a rig with an adapter and the tool is available.
    pytest.fail("real_measurement_available() returned True but no rig wiring in test env")
