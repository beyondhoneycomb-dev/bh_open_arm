"""CG-4A-07d — a relative-action policy is blocked on `sync`; RTC is allowed.

`FR-INF-015`: a relative-action policy cannot run inline (`sync`); the session must
force RTC. The gate fires at backend selection with a distinct reason, and — the
positive control — the same relative-action policy switches to RTC without complaint,
proving the block is specific to `sync`, not a blanket refusal.
"""

from __future__ import annotations

import pytest

from backend.actuation import ManualClock, TargetMailbox
from backend.inference.adapter import (
    ActParams,
    InferenceBackend,
    InferenceParamError,
    InferenceParamReason,
    InferenceSession,
    RtcParams,
)
from tests.wp4a07.support import FixturePolicy, make_dummy_robot


def _session(relative_action: bool) -> InferenceSession:
    """Build a session over a connected dummy with a policy of the given relativity."""
    return InferenceSession(
        robot=make_dummy_robot(),
        mailbox=TargetMailbox(),
        clock=ManualClock(),
        policy=FixturePolicy(relative_action=relative_action),
        fps=30.0,
    )


def test_relative_action_policy_blocks_sync() -> None:
    """Switching a relative-action policy to `sync` raises the relative-action reason."""
    session = _session(relative_action=True)
    with pytest.raises(InferenceParamError) as excinfo:
        session.switch_backend(InferenceBackend.SYNC, ActParams())
    assert excinfo.value.reason is InferenceParamReason.RELATIVE_ACTION_REQUIRES_RTC


def test_relative_action_policy_allows_rtc() -> None:
    """The same relative-action policy switches to RTC — the block is specific to sync."""
    session = _session(relative_action=True)
    session.switch_backend(InferenceBackend.RTC, RtcParams())
    assert session.backend is InferenceBackend.RTC


def test_absolute_action_policy_allows_sync() -> None:
    """A non-relative policy runs on `sync` (the gate does not over-fire)."""
    session = _session(relative_action=False)
    session.switch_backend(InferenceBackend.SYNC, ActParams())
    assert session.backend is InferenceBackend.SYNC
