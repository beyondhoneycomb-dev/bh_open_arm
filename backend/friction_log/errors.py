"""Failure types for the no-transmit logging tap (WP-2B-05).

Two of these encode a gate outcome rather than an ordinary programming error:

- `LoggerTransmitError` is the FAIL_BLOCKING signal behind acceptance ①. A logger
  that transmits on the bus is a second CAN writer, which violates I-1 (one writer
  for the whole torque-ON window) and drops a brakeless arm. It is raised, never
  swallowed — the invariant it guards is the difference between a held arm and a
  dropped one.
- `HardwareDeferredError` marks the acceptance items that cannot be decided on a host
  with no CAN bus (②③④⑤⑦). The machinery is built and unit-tested here; the
  measurement it stands in for is re-run on the rig through `backend.friction_log.reverify`.
"""

from __future__ import annotations


class LoggerTransmitError(RuntimeError):
    """A CAN transmit was found on the logger path (acceptance ①, FAIL_BLOCKING).

    Two CAN writers on one bus is an I-1 violation: the scheduler is the sole writer
    from torque-on to torque-off, and a logger that sends contends the bus and drops
    the arm. Raised by the static scan and by the one-writer re-verification hook; it
    is a real raise, not an `assert`, because it is unstrippable safety.
    """


class HardwareDeferredError(RuntimeError):
    """An acceptance item needs a real CAN bus and cannot be decided on this host.

    Raised by the `reverify` hooks for ②③④⑤⑦ when they are called without the rig
    evidence they require, so a deferred check fails loudly rather than reporting a
    green it never earned. A synthetic-data call must never be presented as a PASS.
    """
