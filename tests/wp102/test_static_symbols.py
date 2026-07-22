"""Acceptance ②/③/④: static checks over the AST, not the prose.

- ② `enable_torque`/`enable_all` are called nowhere on the bring-up path (torque OFF).
- ③ the 0xFE set-zero is emitted from exactly one site in the whole product codebase.
- ④ the 0xAA flash-store is never emitted (firmware-unreliable).
"""

from __future__ import annotations

from tests.wp102 import _source_scan


def test_no_torque_enable_calls_in_product_code() -> None:
    """No product code calls `enable_torque`/`enable_all` — WP-1-02 has no torque-ON path (②)."""
    files = _source_scan.WP102_FILES
    assert _source_scan.count_calls(files, "enable_torque") == 0
    assert _source_scan.count_calls(files, "enable_all") == 0


def test_single_0xfe_emission_site() -> None:
    """`set_zero_position` is called from exactly one product site (③)."""
    assert _source_scan.count_calls(_source_scan.product_files(), "set_zero_position") == 1


def test_no_0xaa_flash_store() -> None:
    """No 0xAA flash-store: neither the command byte nor a save-param symbol appears (④)."""
    files = _source_scan.WP102_FILES
    assert not _source_scan.uses_int_constant(files, _source_scan.SAVE_PARAM_BYTE)
    for symbol in _source_scan.SAVE_PARAM_NAMES:
        assert not _source_scan.references_symbol(files, symbol), f"{symbol} referenced"
