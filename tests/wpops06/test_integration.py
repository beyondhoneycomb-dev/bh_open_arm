"""The producer bridges resolve real upstream types to registry symbols.

Exercises the WP-0B-01 lock, WP-0A-02 action-contract and WP-OPS-05 logger
consumption points so the declared dependencies are real, not fake imports.
"""

from __future__ import annotations

from backend.can.lock import AcquireResult
from contracts.action import ClampReason
from contracts.errors.integration import code_for_clamp, code_for_lock_failure, log_error
from ops.telemetry.structured_log import StructuredLogger


def test_lock_failure_maps_to_oa_can_004() -> None:
    """A refused CAN writer-lock acquisition resolves to OA-CAN-004 (WP-0B-01)."""
    failed = AcquireResult(ok=False, held=(), blocked_iface="can0", holder=None)
    acquired = AcquireResult(ok=True, held=("can0",), blocked_iface=None, holder=None)
    assert code_for_lock_failure(failed) == "OA-CAN-004"
    assert code_for_lock_failure(acquired) is None


def test_clamp_reason_maps_to_control_codes() -> None:
    """Action-contract clamp reasons resolve to their codes (WP-0A-02)."""
    assert code_for_clamp(ClampReason.JOINT_LIMIT) == "OA-CTL-002"
    assert code_for_clamp(ClampReason.STALE_SOURCE) == "OA-CTL-004"
    assert code_for_clamp(ClampReason.NONE) is None


def test_log_error_emits_through_the_ops05_logger() -> None:
    """A code is emitted as a structured record via the WP-OPS-05 logger."""
    captured = []
    logger = StructuredLogger()
    logger.add_sink(captured.append)
    record = log_error(logger, "OA-SYS-004", pid=1234)
    assert record.event == "OA-SYS-004"
    assert record.subsystem == "system"
    assert record.fields["pid"] == 1234
    assert captured == [record]
