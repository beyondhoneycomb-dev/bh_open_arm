"""A deliberate read-only-contract violation, used to prove the write-symbol scan bites.

This file is never imported. It is fed to `find_write_symbols` by path so the test
can assert the scan reports a write path where one exists. It is not product code —
its whole purpose is to contain the write verbs (`set_zero`, `write_param`) and the
command bytes (`0x55`, `0xFE`) that the real tree must never contain.
"""

from __future__ import annotations

WRITE_PARAM_CMD = 0x55
SET_ZERO_CMD = 0xFE


def set_zero(motor_id: int) -> int:
    """A forbidden set-zero write path, present only so the scan has something to find."""
    return SET_ZERO_CMD


def write_param(motor_id: int, value: int) -> int:
    """A forbidden write-param path (0x55), present only to be detected."""
    return WRITE_PARAM_CMD
