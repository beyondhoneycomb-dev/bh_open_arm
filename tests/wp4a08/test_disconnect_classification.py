"""CG-4A-08d — transport disconnect and empty-action classify to DIFFERENT error codes.

`FR-INF-046` refuses to lump remote failures: a transport loss and an empty-action have
different causes and recoveries. This asserts the two classify to distinct registry
codes (`OA-INF-001` vs `OA-INF-002`), that stale/session/wall-age and a queue-wait land
in their own classes, and that a queue-wait is NOT a network disconnect (it is a
queue-wait timeout, not a network timeout).
"""

from __future__ import annotations

from dataclasses import replace

from backend.inference.runaway import (
    DisconnectClass,
    classify_remote,
    error_code_for,
    is_network_disconnect,
)
from tests.wp4a08.support import flat_vector, healthy_remote


def test_transport_and_empty_action_are_different_codes() -> None:
    """A transport loss and an empty-action classify to two distinct registry codes."""
    transport = replace(healthy_remote(), transport_ok=False)
    empty = replace(healthy_remote(), action=[])

    transport_class = classify_remote(transport)
    empty_class = classify_remote(empty)

    assert transport_class is DisconnectClass.TRANSPORT
    assert empty_class is DisconnectClass.EMPTY_ACTION
    transport_code = error_code_for(transport_class)
    empty_code = error_code_for(empty_class)
    assert transport_code != empty_code
    assert transport_code == "OA-INF-001"
    assert empty_code == "OA-INF-002"


def test_transport_variants_all_classify_transport() -> None:
    """RPC-deadline and readiness failures are transport, decided before action contents."""
    assert classify_remote(replace(healthy_remote(), rpc_deadline_exceeded=True)) is (
        DisconnectClass.TRANSPORT
    )
    assert classify_remote(replace(healthy_remote(), ready_ok=False)) is DisconnectClass.TRANSPORT
    # A dead channel that also returned nothing is TRANSPORT, not EMPTY_ACTION.
    dead_and_empty = replace(healthy_remote(), transport_ok=False, action=[])
    assert classify_remote(dead_and_empty) is DisconnectClass.TRANSPORT


def test_stale_action_classes_are_network() -> None:
    """Session-epoch and wall-age violations are stale-action, a network/session class."""
    epoch = replace(healthy_remote(), session_epoch=2, expected_epoch=1)
    aged = replace(healthy_remote(), observation_wall_age_sec=5.0, max_wall_age_sec=2.0)
    assert classify_remote(epoch) is DisconnectClass.STALE_ACTION
    assert classify_remote(aged) is DisconnectClass.STALE_ACTION
    assert is_network_disconnect(DisconnectClass.STALE_ACTION) is True


def test_queue_wait_timeout_is_not_a_network_disconnect() -> None:
    """`obs_queue_timeout` classifies distinctly and is not a network timeout (`FR-INF-046`)."""
    queue_wait = replace(healthy_remote(), queue_wait_timed_out=True)
    verdict = classify_remote(queue_wait)
    assert verdict is DisconnectClass.QUEUE_WAIT_TIMEOUT
    assert is_network_disconnect(verdict) is False
    assert is_network_disconnect(DisconnectClass.TRANSPORT) is True


def test_healthy_remote_classifies_none() -> None:
    """A fully healthy remote with a real action classifies as no failure."""
    assert classify_remote(healthy_remote(action=flat_vector(1.0))) is None
