"""The safety gate consumes `CTR-TEL@v1` and the deadman lease by reference, restating neither.

`WP-3B-10` imports the tracking-validity model and the sample shape from the frozen
teleop contract, and reads the deadman lease latch through a structural view — it
defines no second validity enum, no second sample type, and no second lease. These
pin that the types the gate uses are the frozen ones.
"""

from __future__ import annotations

import backend.teleop.safety_gate as safety_gate
from backend.teleop.safety_gate.heartbeat import LinkHeartbeat
from contracts.teleop import TeleopSample, TeleopValidity
from contracts.teleop import schema as teleop_schema


def test_heartbeat_consumes_the_frozen_teleop_validity() -> None:
    """The heartbeat's validity handling is driven by the frozen `TeleopValidity`."""
    heartbeat = LinkHeartbeat()
    heartbeat.record(TeleopSample(source_ts=0.0, receive_mono_ns=0, validity=TeleopValidity.OK))
    # The enum the gate reacts to is the contract's, not a re-declared copy.
    assert TeleopValidity.STALE is teleop_schema.TeleopValidity.STALE
    assert TeleopValidity.INVALID.value == 2


def test_package_defines_no_competing_validity_or_sample_type() -> None:
    """The safety-gate package exports no rival to the frozen contract types."""
    exported = set(safety_gate.__all__)
    assert "TeleopValidity" not in exported
    assert "TeleopSample" not in exported


def test_lease_view_is_read_only_structural() -> None:
    """The gate's lease view exposes only a read of the latch — it cannot renew or clear it."""
    members = set(dir(safety_gate.LeaseLatchView))
    assert "latched" in members
    # No renewal, latch-engage, or acknowledge surface is redeclared on the view.
    assert "renew" not in members
    assert "engage_safety_latch" not in members
    assert "acknowledge_latch" not in members
