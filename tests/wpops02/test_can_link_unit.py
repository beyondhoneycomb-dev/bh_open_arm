"""The CAN setup unit renders the bring-up the backend is forbidden to run (acceptance ① half).

The on-boot measurement of ① is hardware-bound and deferred; what runs here is that the
unit's content is correct — every fixed name is brought up as CAN-FD at the verified
bitrates with the raised queue length, in a oneshot unit whose success the backend can gate
on.
"""

from __future__ import annotations

from ops.systemd.can_link import (
    link_setup_commands,
    render_can_link_unit,
    unit_sets_the_link,
)
from ops.systemd.constants import (
    INTERFACE_NAMES,
    LINK_BITRATE,
    LINK_DBITRATE,
    LINK_TXQUEUELEN,
    UDEV_SETTLE_UNIT,
)


def test_every_fixed_name_is_brought_up_as_can_fd() -> None:
    """Each of the four names gets a CAN-FD bring-up at the verified bitrates."""
    unit = render_can_link_unit()
    for name in INTERFACE_NAMES:
        assert (
            f"ip link set {name} up type can bitrate {LINK_BITRATE} dbitrate {LINK_DBITRATE} fd on"
        ) in unit


def test_every_fixed_name_raises_txqueuelen() -> None:
    """Each name gets the FR-SYS-011 queue-length command (1000, not the kernel default)."""
    unit = render_can_link_unit()
    assert LINK_TXQUEUELEN == 1000
    for name in INTERFACE_NAMES:
        assert f"ip link set {name} txqueuelen {LINK_TXQUEUELEN}" in unit


def test_unit_is_oneshot_and_ordered_after_udev_settle() -> None:
    """Oneshot + RemainAfterExit make success gate-able; After=udev-settle orders naming first."""
    unit = render_can_link_unit()
    assert "Type=oneshot" in unit
    assert "RemainAfterExit=yes" in unit
    assert f"After={UDEV_SETTLE_UNIT}" in unit


def test_link_setup_commands_pair_up_and_queue_per_channel() -> None:
    """Every channel yields exactly two commands: bring-up then queue length."""
    commands = link_setup_commands(INTERFACE_NAMES)
    assert len(commands) == 2 * len(INTERFACE_NAMES)
    assert sum(1 for command in commands if "up type can" in command) == len(INTERFACE_NAMES)
    assert sum(1 for command in commands if "txqueuelen" in command) == len(INTERFACE_NAMES)


def test_unit_actually_sets_the_link() -> None:
    """The rendered unit carries the link mutation (positive half of the ② split)."""
    assert unit_sets_the_link(render_can_link_unit())
