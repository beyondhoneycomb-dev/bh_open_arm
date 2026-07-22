"""Acceptance ⑰ — the ERR-nibble decoder maps every known code, unknown is an explicit error.

The Damiao feedback frame carries an ERR nibble upstream discards. The gateway's
decoder maps every known nibble — the disabled baseline, the Enable normal state, and
the seven fault nibbles `8..E` — and, crucially, treats an unrecognised nibble as an
explicit error rather than a silent "healthy" (`14` §2.4). Silently ignoring an
unknown status is the failure this rejects.
"""

from __future__ import annotations

import pytest

from backend.actuation import UnknownErrNibbleError, decode_motor_err
from contracts.errors.constants import DAMIAO_ENABLE_NIBBLE, DAMIAO_ERROR_NIBBLES

# Nibbles with no registered meaning: not the disabled baseline (0), not Enable (1),
# and not one of the seven fault nibbles 8..E.
_UNKNOWN_NIBBLES = (0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0xF)


def _status_byte(nibble: int) -> int:
    """Pack an ERR nibble into the high nibble of a status byte."""
    return nibble << 4


def test_all_seven_fault_nibbles_map_to_codes() -> None:
    """Every one of the seven fault nibbles decodes to an OA-MOT code and is a fault (⑰)."""
    for nibble_hex in DAMIAO_ERROR_NIBBLES:
        decoded = decode_motor_err(_status_byte(int(nibble_hex, 16)))
        assert decoded.code is not None
        assert decoded.code.startswith("OA-MOT-")
        assert decoded.is_fault


def test_enable_state_is_known_and_not_a_fault() -> None:
    """The Enable normal state maps to no code and is not a fault (⑰)."""
    decoded = decode_motor_err(_status_byte(DAMIAO_ENABLE_NIBBLE))
    assert decoded.code is None
    assert not decoded.is_fault


def test_disabled_baseline_is_known_and_not_a_fault() -> None:
    """Nibble 0 (disabled) maps to the baseline code and is not a fault (⑰)."""
    decoded = decode_motor_err(_status_byte(0x0))
    assert decoded.code == "OA-MOT-000"
    assert not decoded.is_fault


@pytest.mark.parametrize("nibble", _UNKNOWN_NIBBLES)
def test_unknown_nibble_is_an_explicit_error(nibble: int) -> None:
    """An unrecognised nibble raises rather than being silently treated as healthy (⑰)."""
    with pytest.raises(UnknownErrNibbleError):
        decode_motor_err(_status_byte(nibble))
