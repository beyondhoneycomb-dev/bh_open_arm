"""RUNS-HERE ① — the per-controller sum over a synthetic `lsusb -t` topology.

The parse, the `serial → bus` reconciliation, and the per-controller sum all run
against the synthetic tree here. The only deferred half is obtaining a real tree and
a real serial-to-bus map from an attached camera, which this host has none of; that
is covered by the live-`lsusb` smoke test below, which parses the host's own bus and
skips with a reason when the binary is absent.
"""

from __future__ import annotations

import pytest

from backend.sensing.bandwidth.budget import evaluate_budget_with_topology
from backend.sensing.bandwidth.topology import (
    assign_controllers,
    lsusb_available,
    parse_lsusb_tree,
    run_lsusb_tree,
)
from tests.wp3b02 import fixtures


def test_tree_parses_into_two_controllers() -> None:
    """The synthetic tree yields usb3 (two cameras) and usb4 (one)."""
    topology = parse_lsusb_tree(fixtures.SYNTHETIC_TREE)
    assert topology.controller_ids() == ("usb3", "usb4")
    usb3, usb4 = topology.controllers
    assert len(usb3.camera_devices()) == 2
    assert len(usb4.camera_devices()) == 1
    assert usb3.link_speed_mbps == 5000


def test_bus_absent_from_tree_is_a_mismatch() -> None:
    """A serial mapped to a bus the tree does not have raises, never defaults."""
    topology = parse_lsusb_tree(fixtures.SYNTHETIC_TREE)
    with pytest.raises(KeyError):
        topology.controller_id_for_bus(9)


def test_assignment_stamps_controller_from_bus() -> None:
    """Reconciliation replaces the placeholder controller with the tree's usbN id."""
    topology = parse_lsusb_tree(fixtures.SYNTHETIC_TREE)
    stamped = assign_controllers(
        fixtures.topology_cameras(), topology, fixtures.SYNTHETIC_SERIAL_TO_BUS
    )
    by_serial = {descriptor.serial: descriptor.controller for descriptor in stamped}
    assert by_serial[fixtures.SERIAL_SHARED_A] == "usb3"
    assert by_serial[fixtures.SERIAL_SHARED_B] == "usb3"
    assert by_serial[fixtures.SERIAL_SOLO_C] == "usb4"


def test_unmapped_serial_raises() -> None:
    """A camera with no bus in the map corrupts the sum, so it must raise."""
    topology = parse_lsusb_tree(fixtures.SYNTHETIC_TREE)
    with pytest.raises(KeyError):
        assign_controllers(fixtures.topology_cameras(), topology, {fixtures.SERIAL_SHARED_A: 3})


def test_per_controller_sum_groups_shared_bus() -> None:
    """The two cameras on usb3 sum together; usb4 is summed apart (FR-CAM-005)."""
    topology = parse_lsusb_tree(fixtures.SYNTHETIC_TREE)
    decision = evaluate_budget_with_topology(
        fixtures.topology_cameras(),
        topology,
        fixtures.SYNTHETIC_SERIAL_TO_BUS,
        effective_cap_mbps=10_000.0,
    )
    per_controller = decision.verdict.per_controller_mbps
    assert set(per_controller) == {"usb3", "usb4"}
    assert per_controller["usb3"] == pytest.approx(2 * 147.456)
    assert per_controller["usb4"] == pytest.approx(147.456)
    assert not decision.blocked


def test_controller_sum_alone_blocks() -> None:
    """A single controller over the cap blocks even when the aggregate would pass."""
    topology = parse_lsusb_tree(fixtures.SYNTHETIC_TREE)
    decision = evaluate_budget_with_topology(
        fixtures.topology_cameras(),
        topology,
        fixtures.SYNTHETIC_SERIAL_TO_BUS,
        effective_cap_mbps=200.0,
    )
    assert decision.blocked
    assert any("usb3" in reason for reason in decision.verdict.reasons)
    assert all("usb4" not in reason for reason in decision.verdict.reasons)


def test_live_lsusb_tree_parses_or_skips() -> None:
    """The live path runs: parse the host's own tree, or skip when lsusb is absent.

    Correlating a camera to a controller stays deferred (no attached camera), so this
    asserts only that the real tree parses into at least one controller.
    """
    if not lsusb_available():
        pytest.skip("lsusb not installed: live USB-topology parse deferred to real hardware")
    topology = parse_lsusb_tree(run_lsusb_tree())
    assert topology.controllers
    assert all(controller.controller_id.startswith("usb") for controller in topology.controllers)
