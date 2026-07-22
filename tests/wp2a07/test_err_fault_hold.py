"""Acceptance ① / ② — the seven ERR codes decode, and each latches a Cat-2 hold.

① Each of the seven Damiao fault nibbles (8,9,A,B,C,D,E) is injected as a synthetic
   status byte and decoded, through the reused Wave-1 decoder, to its `OA-MOT` code.
② A decoded fault latches a Cat-2 hold immediately, in the detecting cycle.

The decode is not re-implemented here or in the watchdog — it is
`backend.actuation.decode_motor_err` (`WP-1-03` ⑰). This suite checks the wiring the
decoder deliberately does not do: a fault becomes a latched safety hold.
"""

from __future__ import annotations

import pytest

from backend.actuation import decode_motor_err
from backend.commloss import WATCHDOG_GATE_PREFIX, WatchdogCause
from contracts.errors.constants import DAMIAO_ENABLE_NIBBLE, DAMIAO_ERROR_NIBBLES
from tests.wp2a07.support import build_watchdog, frames, status_byte


@pytest.mark.parametrize("nibble_hex", DAMIAO_ERROR_NIBBLES)
def test_each_fault_nibble_decodes_and_latches(nibble_hex: str) -> None:
    """Each of the seven fault nibbles injects, decodes to its code, and latches (①②)."""
    nibble = int(nibble_hex, 16)
    expected = decode_motor_err(status_byte(nibble))
    watchdog, latch, _ = build_watchdog()

    verdict = watchdog.service(frames(status_byte(nibble)))

    assert verdict.latched
    assert verdict.newly_latched
    assert verdict.cause is WatchdogCause.MOTOR_FAULT
    assert verdict.motor_code == expected.code

    code = expected.code
    assert code is not None and code.startswith("OA-MOT-")
    # The Cat-2 hold is engaged in the same cycle and attributable to this watchdog.
    assert latch.is_active
    assert latch.reason is not None
    assert latch.reason.gate_id.startswith(WATCHDOG_GATE_PREFIX)
    assert code in latch.reason.gate_id
    assert latch.reason.new_state == "LATCHED"


@pytest.mark.parametrize("nibble", [DAMIAO_ENABLE_NIBBLE, 0x0])
def test_healthy_frames_do_not_latch(nibble: int) -> None:
    """The enable state and disabled baseline are not faults — no latch (②, no over-eager stop)."""
    watchdog, latch, _ = build_watchdog()
    verdict = watchdog.service(frames(status_byte(nibble)))
    assert not verdict.latched
    assert not latch.is_active


def test_unknown_status_latches_fail_closed() -> None:
    """A nibble the decoder cannot vouch for latches fail-closed, never passes as healthy."""
    watchdog, latch, _ = build_watchdog()
    # 0x5 is neither the enable state, the disabled baseline, nor a fault nibble.
    verdict = watchdog.service(frames(status_byte(0x5)))
    assert verdict.latched
    assert verdict.cause is WatchdogCause.UNKNOWN_STATUS
    assert latch.is_active


def test_one_faulted_motor_in_a_cycle_latches_the_arm() -> None:
    """A single faulted motor among healthy frames latches the whole arm (②)."""
    watchdog, latch, _ = build_watchdog()
    verdict = watchdog.service(
        frames(
            status_byte(DAMIAO_ENABLE_NIBBLE),
            status_byte(0xA),
            status_byte(DAMIAO_ENABLE_NIBBLE),
        )
    )
    assert verdict.latched
    assert verdict.cause is WatchdogCause.MOTOR_FAULT
    assert verdict.motor_code == decode_motor_err(status_byte(0xA)).code
    assert latch.is_active
