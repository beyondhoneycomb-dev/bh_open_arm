"""The ethtool -i parser and in-tree gs_usb classification (acceptance ①, parser half).

Parsing runs here; the live `ethtool -i` against a real adapter is deferred.
"""

from __future__ import annotations

from pathlib import Path

from ops.hw.udev.ethtool import is_in_tree_driver, parse_ethtool_i

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ethtool"


def test_gs_usb_output_parses_as_in_tree() -> None:
    """A gs_usb ethtool block parses and classifies as the in-tree family."""
    report = parse_ethtool_i((_FIXTURES / "gs_usb.txt").read_text(encoding="utf-8"))
    assert report.driver == "gs_usb"
    assert report.bus_info == "1-1.2:1.0"
    assert is_in_tree_driver(report) is True


def test_foreign_driver_is_not_in_tree_family() -> None:
    """A non-gs_usb driver parses fine but is not the expected in-tree family."""
    report = parse_ethtool_i((_FIXTURES / "foreign.txt").read_text(encoding="utf-8"))
    assert report.driver == "peak_usb"
    assert is_in_tree_driver(report) is False
