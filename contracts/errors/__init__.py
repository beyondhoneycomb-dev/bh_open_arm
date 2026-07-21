"""CTR-ERR@v1 — the OA-* canonical error-code registry (14 §2.10).

The public surface: `REGISTRY` and `codes` for consumers naming a code by symbol,
`emit`/`make_error`/`OaError` for the sanctioned emission path, `Severity` for the
four fixed levels, and `parse_motor_err` for the Damiao ERR field upstream drops.
The registry data lives in `error_registry.yaml` (frozen, CONTRACT_FROZEN); this
package reads it and never writes it.
"""

from __future__ import annotations

from contracts.errors.constants import CONTRACT_ID, DOMAINS
from contracts.errors.damiao_map import MotorErr, parse_motor_err
from contracts.errors.emission import OaError, emit, make_error
from contracts.errors.registry import (
    REGISTRY,
    ErrorCode,
    Registry,
    UnregisteredCodeError,
    codes,
    load_registry,
)
from contracts.errors.severity import Severity, is_valid_severity

__all__ = [
    "CONTRACT_ID",
    "DOMAINS",
    "REGISTRY",
    "ErrorCode",
    "MotorErr",
    "OaError",
    "Registry",
    "Severity",
    "UnregisteredCodeError",
    "codes",
    "emit",
    "is_valid_severity",
    "load_registry",
    "make_error",
    "parse_motor_err",
]
