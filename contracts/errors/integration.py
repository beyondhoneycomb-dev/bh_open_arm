"""Bridges from the producers WP-OPS-06 consumes to the OA-* codes.

WP-OPS-06 consumes three upstream producers as more than sequencing: the WP-OPS-05
structured logger is the emission target, the WP-0B-01 CAN writer-lock failure is
exactly `OA-CAN-004`, and the WP-0A-02 action contract's `ClampReason` is a control
code. Each is a real import here, so the declared dependency is visible in the
reference graph (`06` §5.6 / CI-16) rather than asserted only in prose.

These bridges are the sanctioned consumption points: they resolve a producer's
own type to a registry symbol, never to an inline code literal.
"""

from __future__ import annotations

from typing import Any

from backend.can.lock import AcquireResult
from contracts.action import ClampReason
from contracts.errors.registry import REGISTRY, codes
from ops.telemetry.structured_log import LogRecord, StructuredLogger

# The action contract's clamp reasons, mapped to the control/motor codes that name
# the same event. NONE is not a fault, so it maps to no code.
_CLAMP_TO_CODE: dict[ClampReason, str] = {
    ClampReason.JOINT_LIMIT: codes.OA_CTL_002,
    ClampReason.TORQUE_LIMIT: codes.OA_MOT_00E,
    ClampReason.STALE_SOURCE: codes.OA_CTL_004,
    ClampReason.SAFETY_LATCH: codes.OA_CTL_003,
}


def code_for_lock_failure(result: AcquireResult) -> str | None:
    """Return the code for a CAN writer-lock acquisition failure (WP-0B-01).

    `OA-CAN-004` (double occupancy / unauthorized writer) is precisely the failure
    the WP-0B-01 lock reports, so a refused acquisition resolves straight to it.

    Args:
        result: The all-or-nothing acquisition outcome.

    Returns:
        (str | None) `OA-CAN-004` on failure, None when the lock was acquired.
    """
    if result.ok:
        return None
    return codes.OA_CAN_004


def code_for_clamp(reason: ClampReason) -> str | None:
    """Return the code naming an action-contract clamp reason (WP-0A-02).

    Args:
        reason: The clamp reason from the frozen action contract.

    Returns:
        (str | None) The mapped code, or None for `ClampReason.NONE`.
    """
    return _CLAMP_TO_CODE.get(reason)


def log_error(logger: StructuredLogger, code: str, **fields: Any) -> LogRecord:
    """Emit a registered code as a record through the WP-OPS-05 logger.

    Args:
        logger: The structured logger to emit through.
        code: The code string, from a `codes` symbol.
        **fields: Extra payload merged into the record's fields.

    Returns:
        (LogRecord) The emitted record.

    Raises:
        UnregisteredCodeError: When the code is not registered.
    """
    entry = REGISTRY.get(code)
    return logger.emit(
        entry.subsystem,
        entry.code,
        {"severity": entry.severity, "message_en": entry.message_en, **fields},
    )
