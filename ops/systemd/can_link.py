"""The systemd CAN setup unit — the one place the CAN link is configured (`01` FR-SYS-006).

FR-SYS-006 splits one responsibility in two and forbids merging them: the unit *sets* the
link, the backend *verifies* it and refuses to start on a mismatch. This module renders
the oneshot unit whose `ExecStart` lines bring each fixed-name channel up as CAN-FD at the
verified 1 Mbit/s nominal / 5 Mbit/s data rate and raise `txqueuelen` to the FR-SYS-011
recommendation.

The `ip link set` commands live here as systemd directives, run by systemd at boot — never
as a Python process spawn, which the backend static check (02a WP-OPS-02 ②) forbids in
backend code. Rendering the command as unit text is the whole point: the setting is
data the init system executes, not code the product runs.
"""

from __future__ import annotations

from collections.abc import Sequence

from ops.systemd.constants import (
    CAN_LINK_UNIT,
    INTERFACE_NAMES,
    LINK_BITRATE,
    LINK_DBITRATE,
    LINK_TXQUEUELEN,
    UDEV_SETTLE_UNIT,
)


def link_up_command(iface: str) -> str:
    """Render the `ip link set … up type can …` command for one channel.

    The command carries `bitrate`/`dbitrate`/`fd on` because python-can's SocketCAN backend
    ignores those arguments (`16` §10.1); only bringing the link up here makes CAN-FD real,
    and a link left at CAN 2.0 but opened `fd=True` fails silently (`01` §2.18 trap 5).

    Args:
        iface: The fixed interface name to bring up.

    Returns:
        (str) The bring-up command line.
    """
    return f"ip link set {iface} up type can bitrate {LINK_BITRATE} dbitrate {LINK_DBITRATE} fd on"


def txqueuelen_command(iface: str) -> str:
    """Render the `ip link set … txqueuelen` command for one channel (FR-SYS-011).

    Args:
        iface: The fixed interface name.

    Returns:
        (str) The queue-length command line.
    """
    return f"ip link set {iface} txqueuelen {LINK_TXQUEUELEN}"


def link_setup_commands(ifaces: Sequence[str]) -> tuple[str, ...]:
    """Render the full bring-up command sequence for a set of channels.

    Each channel gets its up-and-configure command followed by its queue-length command,
    in interface order, so the rendered unit's `ExecStart` lines read one channel at a time.

    Args:
        ifaces: Fixed interface names to bring up.

    Returns:
        (tuple[str, ...]) The command lines in execution order.
    """
    commands: list[str] = []
    for iface in ifaces:
        commands.append(link_up_command(iface))
        commands.append(txqueuelen_command(iface))
    return tuple(commands)


def render_can_link_unit(ifaces: Sequence[str] = INTERFACE_NAMES) -> str:
    """Render the complete `openarm-can-link.service` oneshot unit.

    `Type=oneshot` with `RemainAfterExit=yes` makes the unit's success the fact the backend
    is gated on: the link is either fully configured or the unit failed, with no half-way
    "active" state. `After=`/`Wants=` `systemd-udev-settle` orders bring-up after the fixed
    names exist (`01` FR-SYS-008 precedes 006) — `ip link set oa_fl …` cannot address a
    name udev has not yet assigned.

    Args:
        ifaces: Fixed interface names the unit configures.

    Returns:
        (str) The unit file body.
    """
    exec_lines = "\n".join(f"ExecStart=/sbin/{command}" for command in link_setup_commands(ifaces))
    return (
        "[Unit]\n"
        "Description=OpenArm CAN-FD link bring-up (01 FR-SYS-006/011)\n"
        f"After={UDEV_SETTLE_UNIT}\n"
        f"Wants={UDEV_SETTLE_UNIT}\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        "RemainAfterExit=yes\n"
        f"{exec_lines}\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def unit_sets_the_link(unit_body: str) -> bool:
    """Report whether a rendered unit actually performs the link bring-up.

    The FR-SYS-006 split is only real if the *unit* carries the `ip link set` the backend
    is forbidden to run. This is the positive half of acceptance ②: proving the setting
    exists somewhere keeps "backend has zero link-set calls" from passing vacuously against
    a unit that also sets nothing.

    Args:
        unit_body: A rendered unit file body.

    Returns:
        (bool) True when the unit contains a CAN bring-up and a txqueuelen directive.
    """
    return "ip link set" in unit_body and f"txqueuelen {LINK_TXQUEUELEN}" in unit_body


# The link unit's success is what the backend requires; this is its identity for callers
# wiring the boot-order dependency, kept beside the renderer that produces the unit.
LINK_UNIT_NAME = CAN_LINK_UNIT
