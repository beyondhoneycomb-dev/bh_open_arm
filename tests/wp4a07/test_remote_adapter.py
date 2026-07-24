"""The remote-gRPC adapter: validated params, direct `send_action`, and an honest Q8 deferral.

`NFR-INF-008`: the remote client calls `robot.send_action()` directly, so the offline
dummy path routes actions through `send_action` (not the mailbox). `11` §5-Q8 [미확인]:
the end-to-end remote rollout cannot be verified here (no real robot), so it is carried
as a re-verification hook — `verified is False`, with the gate that would close it — and
is never faked green. These tests assert exactly that split: the local path runs, the
e2e is deferred.
"""

from __future__ import annotations

import pytest

from backend.actuation import ManualClock, TargetMailbox
from backend.inference.adapter import (
    BackendNotPublishableError,
    InferenceBackend,
    InferenceSession,
    RemoteInferenceAdapter,
    RemoteParams,
    advisory_max_roundtrip_sec,
)
from contracts.action import BIMANUAL_ACTION_DIM
from tests.wp4a07.support import FixturePolicy, make_dummy_robot


def _remote_session() -> InferenceSession:
    """Build a session switched to the remote backend with a valid actions_per_chunk."""
    session = InferenceSession(
        robot=make_dummy_robot(),
        mailbox=TargetMailbox(),
        clock=ManualClock(),
        policy=FixturePolicy(),
        fps=30.0,
    )
    session.switch_backend(InferenceBackend.REMOTE_GRPC, RemoteParams(actions_per_chunk=8, fps=30))
    return session


def test_remote_e2e_is_deferred_with_a_reverification_hook_not_faked() -> None:
    """The remote adapter carries the Q8 deferral: unverified here, with the gate to close it."""
    session = _remote_session()
    adapter = session.remote_adapter
    assert isinstance(adapter, RemoteInferenceAdapter)
    hook = adapter.reverification_hook
    assert hook.verified is False
    assert hook.question_id == "11#5-Q8"
    assert "policy_server" in hook.reverify_gate
    assert "no real robot" in hook.blocked_reason.lower()


def test_remote_dummy_path_routes_through_send_action_not_the_mailbox() -> None:
    """`dummy_rollout_step` returns the follower's accepted action; the mailbox stays empty."""
    session = _remote_session()
    adapter = session.remote_adapter
    assert adapter is not None

    accepted = adapter.dummy_rollout_step([1.0] * BIMANUAL_ACTION_DIM)
    assert len(accepted) == BIMANUAL_ACTION_DIM
    # The remote path does not publish to the mailbox — the client hits send_action directly.
    assert session.last_published is None


def test_ticking_the_publisher_in_remote_mode_is_refused() -> None:
    """The in-process publisher does not tick in remote mode (no mailbox target)."""
    session = _remote_session()
    with pytest.raises(BackendNotPublishableError):
        session.tick()


def test_remote_roundtrip_bound_matches_the_nfr_inf_001_inequality() -> None:
    """The adapter's advisory bound equals `(threshold * actions_per_chunk) / fps`."""
    session = _remote_session()
    adapter = session.remote_adapter
    assert adapter is not None
    assert adapter.roundtrip_bound_sec == pytest.approx(advisory_max_roundtrip_sec(0.5, 8, 30))


def test_building_remote_adapter_from_unvalidated_params_is_refused() -> None:
    """Defence in depth: the adapter refuses params with a missing actions_per_chunk."""
    with pytest.raises(ValueError):
        RemoteInferenceAdapter(RemoteParams(actions_per_chunk=None), make_dummy_robot())
