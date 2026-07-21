"""The two-axis rule generator: both axes required, can-prefix banned, serial-else-port fallback.

These are the contract's runnable half — rule shape, one-axis rejection, can-prefix
rejection, and the iSerial-absent KERNELS fallback (acceptance ④, ⑦).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ops.hw.udev.model import AdapterAxisKind
from ops.hw.udev.parser import parse_udevadm_info
from ops.hw.udev.rules import (
    CONTRACT_NAMES,
    CanPrefixNameError,
    MissingAxisError,
    build_rule,
    build_rule_for_interface,
    render_ruleset,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "udevadm"


def test_serial_present_binds_serial_axis() -> None:
    """With a serial, the rule pins ATTRS{serial} and ATTR{dev_id} — both axes."""
    rule = build_rule("oa_fl", dev_id="0x0", serial="OA_ADAPTER_A", port_path="1-1.2:1.0")
    assert rule.adapter_axis is AdapterAxisKind.SERIAL
    line = rule.render()
    assert 'ATTRS{serial}=="OA_ADAPTER_A"' in line
    assert 'ATTR{dev_id}=="0x0"' in line
    assert 'NAME="oa_fl"' in line
    assert 'ATTR{type}=="280"' in line


def test_iserial_absent_falls_back_to_kernels_port_path() -> None:
    """Acceptance ④: no serial → the adapter axis is the KERNELS port path."""
    rule = build_rule("oa_fl", dev_id="0x0", serial=None, port_path="1-1.2:1.0")
    assert rule.adapter_axis is AdapterAxisKind.PORT_PATH
    line = rule.render()
    assert 'KERNELS=="1-1.2:1.0"' in line
    assert "ATTRS{serial}" not in line
    assert 'ATTR{dev_id}=="0x0"' in line


def test_missing_channel_axis_is_rejected() -> None:
    """A rule with no dev_id is one-axis → rejected at store (contract)."""
    with pytest.raises(MissingAxisError):
        build_rule("oa_fl", dev_id=None, serial="OA_ADAPTER_A", port_path="1-1.2:1.0")


def test_missing_adapter_axis_is_rejected() -> None:
    """A rule with neither serial nor port path is one-axis → rejected."""
    with pytest.raises(MissingAxisError):
        build_rule("oa_fl", dev_id="0x0", serial=None, port_path=None)


def test_can_prefixed_name_is_rejected() -> None:
    """Acceptance ⑦ at generation time: a `can`-prefixed name is refused."""
    with pytest.raises(CanPrefixNameError):
        build_rule("can9", dev_id="0x0", serial="OA_ADAPTER_A", port_path="1-1.2:1.0")


def test_full_ruleset_binds_the_four_contract_names() -> None:
    """The four fixed names render into a two-axis rule set from parsed interfaces."""
    dumps = ["can0_serial.txt", "can1_serial.txt", "can2_serial.txt", "can3_serial.txt"]
    interfaces = [
        parse_udevadm_info((_FIXTURES / name).read_text(encoding="utf-8")) for name in dumps
    ]
    rules = tuple(
        build_rule_for_interface(name, interface)
        for name, interface in zip(CONTRACT_NAMES, interfaces, strict=True)
    )
    body = render_ruleset(rules)
    for name in CONTRACT_NAMES:
        assert f'NAME="{name}"' in body
    # Every rendered rule carries both axes.
    assert body.count("ATTR{dev_id}") == 4
    assert body.count("ATTRS{serial}") == 4


def test_port_swap_semantics_documented_per_axis() -> None:
    """Acceptance ⑥: serial-axis names survive a port swap; port-path names do not."""
    assert AdapterAxisKind.SERIAL.port_swap_stable is True
    assert AdapterAxisKind.PORT_PATH.port_swap_stable is False
