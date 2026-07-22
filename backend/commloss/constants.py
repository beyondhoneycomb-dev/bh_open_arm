"""Named parameters of the comm-loss watchdog (`WP-2A-07`).

Every literal the watchdog's decision logic depends on is named here rather than
spelled at a call site, so the one place a threshold is decided is the one place
it is read (`14` §2, constants rule).
"""

from __future__ import annotations

# Receive-side silence ceiling: a `recv_all()` that returns nothing for at least
# this long is a comm loss and forces a safe stop (`04` FR-MAN-056, `12`
# FR-SAF-027). 10 ms is 10 CAN cycles at the nominal loop rate. This is the RX
# counterpart of `backend/actuation/config.py`'s `RID9_NO_SEND_MARGIN_SEC`, which
# bounds the TX side (how long the scheduler may go between sends); the two watch
# opposite directions of the same bus and are deliberately separate values.
DEFAULT_COMM_TIMEOUT_SEC = 0.010

# The Damiao Clear-Error CAN payload (`12` FR-SAF-028: `FF FF FF FF FF FF FF FB`).
# The watchdog never writes the bus itself (I-1 single-writer); `clear_error`
# returns this payload so the bus owner emits it, and only after operator confirm.
CLEAR_ERROR_PAYLOAD = bytes((0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFB))

# Prefix of the `LatchReason.gate_id` this watchdog stamps, so an audited hold can
# be attributed to the comm-loss watchdog rather than another latch source.
WATCHDOG_GATE_PREFIX = "COMM_LOSS_WATCHDOG"
