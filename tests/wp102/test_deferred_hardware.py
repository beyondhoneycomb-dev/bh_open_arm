"""Deferred hardware acceptances ①/⑥/⑦ — SKIPPED with reason, never asserted.

These three acceptances require 16 real motors, an operator, and a power cycle. None of
that exists on this dev host (no CAN, no motors), and a torque/readback/persistence
green here would be a SAFETY LIE: a human trusts these gates before energising a 40 Nm
arm with no holding brake. So each is SKIPPED with the reason and the concrete re-
verification it needs on a real fixture (plan 02a §4.1). The resume point is
`RESUME-1-02-ZERO`; the offline arithmetic and refusal branches that CAN run are proven
in the other WP-1-02 tests.
"""

from __future__ import annotations

import pytest

# The re-verification hook: the physical procedure each deferred gate must run on a real
# fixture before its evidence is real. Named here so the deferral is a recorded contract,
# not a silent omission (02 FR-CON-065, WP-1-02 resume RESUME-1-02-ZERO).
REVERIFY_HOOK = "RESUME-1-02-ZERO"


@pytest.mark.skip(
    reason=(
        f"HW-DEFERRED ①: is_torque_enabled==False on all 16 motors needs real motors on CAN. "
        f"Re-verify on fixture at {REVERIFY_HOOK}: connect_readonly() then read torque state "
        f"from every motor. Never asserted offline — a faked torque-OFF green is a safety lie."
    )
)
def test_torque_off_on_sixteen_motors() -> None:
    """Deferred: real-motor torque-OFF readback (①)."""
    raise AssertionError("must run on a real fixture; this body must never execute here")


@pytest.mark.skip(
    reason=(
        f"HW-DEFERRED ⑥: the ±0.5° readback residual needs a real 0xFE + encoder readback. "
        f"Re-verify on fixture at {REVERIFY_HOOK}: after 0xFE, read motor_zero_raw and confirm "
        f"the per-joint residual is within tolerance. The residual ARITHMETIC is proven offline "
        f"in test_set_zero_flow; only the physical readback is deferred."
    )
)
def test_zero_readback_residual_within_tolerance() -> None:
    """Deferred: real 0xFE readback residual (⑥)."""
    raise AssertionError("must run on a real fixture; this body must never execute here")


@pytest.mark.skip(
    reason=(
        f"HW-DEFERRED ⑦: 0xFE power-cycle persistence needs a real power re-application. "
        f"Re-verify on fixture at {REVERIFY_HOOK}: power-cycle, reconnect, re-check the residual; "
        f"within tolerance -> record that the zero persists; else keep re-zero forced "
        f"(the conservative default already persisted). Both are valid results; "
        f"neither may be assumed offline."
    )
)
def test_zero_persists_across_power_cycle() -> None:
    """Deferred: real power-cycle persistence re-verify (⑦)."""
    raise AssertionError("must run on a real fixture; this body must never execute here")
