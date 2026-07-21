"""Acceptance ② and ⑥ — USB topology tree, adapter membership, and HS-USB-2.0 check.

Runs on synthetic `lsusb -t` fixtures. It confirms both adapters' root-hub/controller
membership is recorded, the shared-controller question is answered explicitly, and
the 480 Mbps (High-Speed USB 2.0) link speed is recorded (`16` §10.1 claim).
"""

from __future__ import annotations

from pathlib import Path

from ops.hw.usb.topology import HIGH_SPEED_USB2_TOKEN, parse_topology

_FIXTURES = Path(__file__).parent / "fixtures"


def test_two_adapters_on_shared_controller() -> None:
    """Both gs_usb adapters hang off one xHCI controller; sharing is stated True."""
    text = (_FIXTURES / "lsusb_t_shared_controller.txt").read_text(encoding="utf-8")
    report = parse_topology(text)

    assert len(report.adapters) == 2
    buses = {adapter.bus for adapter in report.adapters}
    assert len(buses) == 1, "both adapters should be on one root hub / controller bus"
    assert report.shared_controller is True


def test_two_adapters_on_separate_controllers() -> None:
    """Adapters on distinct controllers are recorded as not sharing."""
    text = (_FIXTURES / "lsusb_t_separate_controllers.txt").read_text(encoding="utf-8")
    report = parse_topology(text)

    assert len(report.adapters) == 2
    assert report.shared_controller is False
    # Each adapter still records which controller it belongs to.
    for adapter in report.adapters:
        assert adapter.controller.startswith("xhci_hcd")
        assert adapter.bus > 0


def test_high_speed_usb2_link_speed_recorded() -> None:
    """The 480M HS-USB-2.0 link speed is captured per adapter (acceptance ⑥)."""
    text = (_FIXTURES / "lsusb_t_shared_controller.txt").read_text(encoding="utf-8")
    report = parse_topology(text)

    assert report.all_high_speed_usb2 is True
    for adapter in report.adapters:
        assert adapter.link_speed == HIGH_SPEED_USB2_TOKEN
        assert adapter.is_high_speed_usb2 is True


def test_topology_serialises_tree_and_membership() -> None:
    """The report projects to the usb_topology.json shape with tree + verdict."""
    text = (_FIXTURES / "lsusb_t_shared_controller.txt").read_text(encoding="utf-8")
    payload = parse_topology(text).as_dict()

    assert payload["shared_controller"] is True
    assert isinstance(payload["buses"], list) and payload["buses"]
    assert len(payload["adapters"]) == 2


def test_no_adapters_leaves_sharing_unanswerable() -> None:
    """With fewer than two adapters, shared_controller is None, not a false claim."""
    report = parse_topology(
        "/:  Bus 001.Port 001: Dev 001, Class=root_hub, Driver=xhci_hcd/2p, 480M"
    )
    assert report.adapters == ()
    assert report.shared_controller is None
    assert report.all_high_speed_usb2 is False
