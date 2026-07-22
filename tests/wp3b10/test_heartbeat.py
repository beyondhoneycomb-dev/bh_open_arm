"""The VR link heartbeat: STALE is a lost link, judged on the server clock (`FR-TEL-081`).

These pin the three lost-link triggers the contract fuses into one verdict — arrival
staleness past the timeout, INVALID validity, and STALE validity under the frozen
`treat_stale_as_lost` — and that the age is measured on the server receive clock, the
authority `CTR-PRIM@v1` pins (never the headset source `t`).
"""

from __future__ import annotations

import pytest

from backend.teleop.safety_gate.constants import (
    MAX_HEARTBEAT_TIMEOUT_MS,
    MIN_HEARTBEAT_TIMEOUT_MS,
    heartbeat_timeout_ns,
)
from backend.teleop.safety_gate.heartbeat import LinkHealth, LinkHeartbeat
from contracts.teleop import TeleopValidity
from tests.wp3b10.conftest import make_sample

_TIMEOUT_NS = 100_000_000  # 100 ms default


def test_link_is_lost_before_any_frame_arrives() -> None:
    """With no frame recorded, the link is lost and the age is undefined."""
    heartbeat = LinkHeartbeat()
    assert heartbeat.age_ns(0) is None
    assert heartbeat.health(0) is LinkHealth.LOST


def test_fresh_ok_frame_is_live_until_the_timeout() -> None:
    """An OK frame keeps the link live up to the timeout, then it is lost."""
    heartbeat = LinkHeartbeat()
    heartbeat.record(make_sample(receive_mono_ns=0, validity=TeleopValidity.OK))
    assert heartbeat.health(0) is LinkHealth.LIVE
    assert heartbeat.health(_TIMEOUT_NS) is LinkHealth.LIVE
    assert heartbeat.health(_TIMEOUT_NS + 1) is LinkHealth.LOST


def test_stale_validity_is_treated_as_a_lost_link() -> None:
    """A STALE(1) frame is a lost link under the frozen `treat_stale_as_lost` (FR-TEL-081)."""
    heartbeat = LinkHeartbeat()
    heartbeat.record(make_sample(receive_mono_ns=0, validity=TeleopValidity.STALE))
    # Fresh in arrival terms, but STALE is indistinguishable downstream from a stop.
    assert heartbeat.age_ns(0) == 0
    assert heartbeat.health(0) is LinkHealth.LOST


def test_invalid_validity_is_a_lost_link() -> None:
    """An INVALID(2) frame is a lost link even when freshly arrived (FR-TEL-081)."""
    heartbeat = LinkHeartbeat()
    heartbeat.record(make_sample(receive_mono_ns=0, validity=TeleopValidity.INVALID))
    assert heartbeat.health(0) is LinkHealth.LOST


def test_stale_tolerated_only_when_policy_disabled() -> None:
    """The STALE-as-lost collapse is exactly `treat_stale_as_lost`; disabling it tolerates STALE.

    This names the negative branch so the frozen default is a real choice: with the
    policy off a STALE frame stays live, which is precisely why the contract freezes it
    on.
    """
    tolerant = LinkHeartbeat(treat_stale_as_lost=False)
    tolerant.record(make_sample(receive_mono_ns=0, validity=TeleopValidity.STALE))
    assert tolerant.health(0) is LinkHealth.LIVE


def test_age_is_measured_on_the_server_receive_clock() -> None:
    """Heartbeat age is `now - receive_mono_ns`, the server clock, not the source `t`."""
    heartbeat = LinkHeartbeat()
    heartbeat.record(
        make_sample(receive_mono_ns=1_000, validity=TeleopValidity.OK, source_ts=999.0)
    )
    # A large, misleading source timestamp does not enter the age; only the server
    # receive instant does.
    assert heartbeat.age_ns(1_050) == 50


def test_timeout_range_is_enforced() -> None:
    """The heartbeat timeout is constrained to the FR-TEL-081 tunable range."""
    assert heartbeat_timeout_ns(MIN_HEARTBEAT_TIMEOUT_MS) > 0
    assert heartbeat_timeout_ns(MAX_HEARTBEAT_TIMEOUT_MS) > 0
    with pytest.raises(ValueError, match="tunable range"):
        heartbeat_timeout_ns(MIN_HEARTBEAT_TIMEOUT_MS - 1)
    with pytest.raises(ValueError, match="tunable range"):
        heartbeat_timeout_ns(MAX_HEARTBEAT_TIMEOUT_MS + 1)
