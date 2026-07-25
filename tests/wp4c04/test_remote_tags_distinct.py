"""CG-4C-04c — REMOTE_DISCONNECT and REMOTE_EMPTY_ACTION are different tags (FR-INF-046)."""

from __future__ import annotations

from backend.eval.taxonomy import (
    CorrelationEngine,
    FailureTag,
    code_for_tag,
    placeholder_taxonomy_thresholds,
)
from backend.inference.runaway import DisconnectClass
from tests.wp4c04.support import signals


def _engine() -> CorrelationEngine:
    return CorrelationEngine(placeholder_taxonomy_thresholds())


def test_transport_disconnect_is_remote_disconnect() -> None:
    """A transport loss auto-derives to REMOTE_DISCONNECT, not REMOTE_EMPTY_ACTION."""
    tags = _engine().correlate(signals(disconnect_class=DisconnectClass.TRANSPORT))
    assert FailureTag.REMOTE_DISCONNECT in tags
    assert FailureTag.REMOTE_EMPTY_ACTION not in tags


def test_empty_action_is_remote_empty_action() -> None:
    """An empty action auto-derives to REMOTE_EMPTY_ACTION, not REMOTE_DISCONNECT."""
    tags = _engine().correlate(signals(disconnect_class=DisconnectClass.EMPTY_ACTION))
    assert FailureTag.REMOTE_EMPTY_ACTION in tags
    assert FailureTag.REMOTE_DISCONNECT not in tags


def test_the_two_remote_tags_are_distinct_members() -> None:
    """They are different enum members and carry different codes (transport vs empty)."""
    assert FailureTag.REMOTE_DISCONNECT is not FailureTag.REMOTE_EMPTY_ACTION
    assert code_for_tag(FailureTag.REMOTE_DISCONNECT) != code_for_tag(
        FailureTag.REMOTE_EMPTY_ACTION
    )


def test_stale_action_is_grouped_with_disconnect() -> None:
    """A stale action is a network/session loss — the same tag as a transport loss."""
    tags = _engine().correlate(signals(disconnect_class=DisconnectClass.STALE_ACTION))
    assert FailureTag.REMOTE_DISCONNECT in tags
    assert FailureTag.REMOTE_EMPTY_ACTION not in tags


def test_queue_wait_timeout_yields_no_remote_tag() -> None:
    """A live-channel queue-wait is neither a disconnect nor an empty action here."""
    tags = _engine().correlate(signals(disconnect_class=DisconnectClass.QUEUE_WAIT_TIMEOUT))
    assert FailureTag.REMOTE_DISCONNECT not in tags
    assert FailureTag.REMOTE_EMPTY_ACTION not in tags
