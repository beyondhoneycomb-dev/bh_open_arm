"""The VR link heartbeat (`FR-TEL-081`): STALE is a lost link, judged on the server clock.

The heartbeat is the teleop analogue of the deadman lease: control is alive only
while fresh, OK-validity VR frames keep arriving, and their absence — for any reason,
including the headset dropping off the network — is a lost link that must decelerate
and hold. A lost link has three triggers, all collapsed here into one `LinkHealth`:

- no fresh frame within `hb_timeout` (default 100 ms), measured as arrival age;
- the latest frame's tracking validity is INVALID(2);
- the latest frame's tracking validity is STALE(1), because `treat_stale_as_lost`
  is frozen true — STALE is indistinguishable downstream from a normal stop.

Age is judged on the SERVER `CLOCK_MONOTONIC` (the frame's receive instant against
now), never on the headset's source timestamp. `CTR-PRIM@v1` pins the source `t` as
an age input only, never the expiry authority (the same rule the deadman lease
enforces), so trusting the client clock for a safety timeout is a contract violation.
This module consumes `TeleopValidity` from the frozen `CTR-TEL@v1` contract and
restates none of it.
"""

from __future__ import annotations

from enum import Enum

from backend.teleop.safety_gate.constants import (
    DEFAULT_HEARTBEAT_TIMEOUT_MS,
    TREAT_STALE_AS_LOST,
    heartbeat_timeout_ns,
)
from contracts.teleop import TeleopSample, TeleopValidity


class LinkHealth(Enum):
    """The VR link's health as the safety gate sees it.

    Only two values, because the whole point of `treat_stale_as_lost` is that STALE
    is not a third, tolerated state: a link is either LIVE (fresh OK frames) or LOST.
    """

    LIVE = "live"
    LOST = "lost"


class LinkHeartbeat:
    """Tracks VR frame arrival and validity, and reports the link LIVE or LOST.

    Ownership: holds the receive instant and tracking validity of the most recent
    frame and the timeout horizon. It reads no clock itself — `health(now_ns)` is
    given the server-clock reading — so it stays deterministic under the fault-
    injection harness. One instance per teleop session.
    """

    def __init__(
        self,
        timeout_ms: int = DEFAULT_HEARTBEAT_TIMEOUT_MS,
        treat_stale_as_lost: bool = TREAT_STALE_AS_LOST,
    ) -> None:
        """Bind the heartbeat to a timeout and the frozen STALE-as-lost policy.

        Args:
            timeout_ms: The heartbeat timeout in milliseconds (`FR-TEL-081` range).
            treat_stale_as_lost: Whether tracking STALE is a lost link; frozen true
                by the `WP-3B-10` contract, exposed only so the negative branch
                (`treat_stale_as_lost = false`) is nameable, never as an operating
                mode.
        """
        self._timeout_ns = heartbeat_timeout_ns(timeout_ms)
        self._treat_stale_as_lost = treat_stale_as_lost
        self._last_receive_ns: int | None = None
        self._last_validity: TeleopValidity | None = None

    @property
    def timeout_ns(self) -> int:
        """The heartbeat timeout in server-clock nanoseconds."""
        return self._timeout_ns

    def record(self, sample: TeleopSample) -> None:
        """Register the arrival of a VR frame.

        Args:
            sample: The received `CTR-TEL@v1` sample; its server-clock receive
                instant and tracking validity are what the heartbeat judges.
        """
        self._last_receive_ns = sample.receive_mono_ns
        self._last_validity = sample.validity

    def age_ns(self, now_ns: int) -> int | None:
        """Return the arrival age of the latest frame, or None if none has arrived.

        Args:
            now_ns: The current server-clock reading, nanoseconds.

        Returns:
            (int | None) `now - last_receive`, or None before the first frame.
        """
        if self._last_receive_ns is None:
            return None
        return now_ns - self._last_receive_ns

    def health(self, now_ns: int) -> LinkHealth:
        """Judge the link LIVE or LOST as of `now_ns`.

        A link is LOST before any frame arrives, once the arrival age exceeds the
        timeout, when the latest validity is INVALID, and — under the frozen policy —
        when the latest validity is STALE.

        Args:
            now_ns: The current server-clock reading, nanoseconds.

        Returns:
            (LinkHealth) LIVE only when a fresh, OK-validity frame is in force.
        """
        age = self.age_ns(now_ns)
        if age is None or age > self._timeout_ns:
            return LinkHealth.LOST
        if self._last_validity == TeleopValidity.INVALID:
            return LinkHealth.LOST
        if self._last_validity == TeleopValidity.STALE and self._treat_stale_as_lost:
            return LinkHealth.LOST
        return LinkHealth.LIVE
