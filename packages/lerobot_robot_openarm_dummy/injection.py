"""The fault-injection state a dummy device carries (FR-OPS-085).

`FaultInjection` is the single mutable knob-set the dummy follower and leader read
to decide whether this cycle is healthy or degraded. It is deliberately plain data
with no behaviour and no device import, so the scenario library, the devices, and
the tests all share one description of "what fault is armed" without a dependency
cycle.

The default is the healthy device: `FaultInjection.none()` arms nothing, and every
field's zero value is "no fault". A dummy with a default injection is
indistinguishable from a well-behaved real device — the faults are opt-in.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Per-observation latency ceiling the response-lag monitor flags against. This is a
# bench budget for the AI-offline harness, NOT a production loop-rate claim: the
# real figure is PG-RT-001a, deliberately unfixed until WP-1-04 (mirrors the stance
# in backend/actuation/config.py). A simulated observation slower than this is an
# overrun the upstream deadline monitor must catch.
OBSERVATION_DEADLINE_SEC = 0.02


class FaultKind(Enum):
    """The kinds of fault the scenario library exercises (acceptance ④).

    Each names a distinct failure a real device exhibits and a distinct upstream
    reaction it must provoke; they are separated so a monitor that conflated two of
    them (one "device broke" bucket) would fail to reproduce the corpus.
    """

    OBSERVATION_MISSING = "observation_missing"
    PACKET_DROP = "packet_drop"
    STALE_SOURCE = "stale_source"
    BUS_OFF = "bus_off"
    PARTIAL_CONNECT = "partial_connect"
    RESPONSE_LAG = "response_lag"


@dataclass
class FaultInjection:
    """What fault, if any, a dummy device is currently told to exhibit.

    Attributes:
        drop_channels: Observation channels to omit from `get_observation`, standing
            in for a sensor that failed to report (obs-missing).
        packet_drop: When True, the follower reuses its last frame and increments
            the CAN drop counter, standing in for a dropped CAN packet (01
            FR-SYS-018).
        fail_channels: Named arm channels that fail to attach on `connect`, standing
            in for a bimanual follower that comes up half-connected.
        response_lag_sec: Simulated seconds a `get_observation` took; when it exceeds
            `OBSERVATION_DEADLINE_SEC` the deadline monitor flags an overrun.
        stall: When True, the leader stops producing fresh actions, standing in for a
            source gone quiet — the mailbox then ages into a stale-source hold.
    """

    drop_channels: tuple[str, ...] = ()
    packet_drop: bool = False
    fail_channels: tuple[str, ...] = ()
    response_lag_sec: float = 0.0
    stall: bool = False

    @staticmethod
    def none() -> FaultInjection:
        """Return the healthy injection: nothing armed.

        Returns:
            (FaultInjection) A device that behaves as a well-formed real one.
        """
        return FaultInjection()
