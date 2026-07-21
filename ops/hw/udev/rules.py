"""Two-axis udev fixed-name rule generator (`01` FR-SYS-008, `02` FR-CON-005).

The contract this module enforces at construction time:

- A rule binds a fixed name on **both** axes — an adapter discriminator
  (`ATTRS{serial}` or the `KERNELS==` port path) **and** the `ATTR{dev_id}` channel
  discriminator. A rule missing either axis is refused, never rendered (`MissingAxisError`).
- The fixed name must not start with `can`: the kernel is concurrently assigning
  `canN`, and a `can`-prefixed udev name races it for the same namespace
  (`CanPrefixNameError`).

The four contract names (`oa_fl`/`oa_fr`/`oa_ll`/`oa_lr`, `02` FR-CON-005) are what
WP-0B-06/07 consume as the stable interface identity — they are frozen here, not
derived from any live enumeration.
"""

from __future__ import annotations

from dataclasses import dataclass

from ops.hw.udev.model import AdapterAxisKind, UdevInterface

# `02` FR-CON-005 — the fixed names are the contract downstream binds to.
NAME_FRONT_LEFT = "oa_fl"
NAME_FRONT_RIGHT = "oa_fr"
NAME_LEFT_LEFT = "oa_ll"
NAME_LEFT_RIGHT = "oa_lr"
CONTRACT_NAMES = (NAME_FRONT_LEFT, NAME_FRONT_RIGHT, NAME_LEFT_LEFT, NAME_LEFT_RIGHT)

# `01` FR-SYS-008 / `02` FR-CON-005 — a fixed name starting with `can` races the
# kernel's own `canN` assignment for the interface namespace.
BANNED_NAME_PREFIX = "can"

# ARPHRD_CAN = 280; every rule pins `ATTR{type}=="280"` so a non-CAN net device can
# never match (`02` §2.5.1).
ARPHRD_CAN_TYPE = "280"

_RULES_FILENAME = "80-openarm-can.rules"


class UdevRuleError(Exception):
    """Base class for a refusal to build or store a fixed-name rule."""


class MissingAxisError(UdevRuleError):
    """A rule was requested without both the adapter axis and the channel axis.

    A one-axis rule is rejected at store time (`01` FR-SYS-008): the adapter axis
    alone cannot tell one adapter's two channels apart, and the channel axis alone
    cannot tell two identical-VID/PID adapters apart.
    """


class CanPrefixNameError(UdevRuleError):
    """A fixed name beginning with `can` was requested (`01` FR-SYS-008)."""


@dataclass(frozen=True)
class UdevRule:
    """A single fixed-name binding, guaranteed two-axis and non-`can`-prefixed.

    Instances are only ever produced through `build_rule`, so the invariants
    (both axes present, legal name) hold by construction — the type itself is the
    proof that a stored rule is not one-axis.

    Attributes:
        name: The fixed interface name (`oa_fl`), never `can`-prefixed.
        adapter_axis: Which discriminator pins the adapter.
        adapter_value: The serial or port-path literal that adapter axis matches.
        dev_id: The `ATTR{dev_id}` channel discriminator (`0x0`/`0x1`).
        arphrd_type: `ATTR{type}` guard, `280` for CAN.
    """

    name: str
    adapter_axis: AdapterAxisKind
    adapter_value: str
    dev_id: str
    arphrd_type: str

    def render(self) -> str:
        """Render this rule as one udev rule line.

        Returns:
            (str) A `SUBSYSTEM=="net" … NAME="<name>"` line matching `02` §2.5.1.
        """
        return (
            'SUBSYSTEM=="net", ACTION=="add", '
            f'ATTR{{type}}=="{self.arphrd_type}", '
            f'{self.adapter_axis.udev_key}=="{self.adapter_value}", '
            f'ATTR{{dev_id}}=="{self.dev_id}", '
            f'NAME="{self.name}"'
        )


def assert_legal_name(name: str) -> None:
    """Reject a fixed name that would race the kernel's `canN` namespace.

    Args:
        name: Proposed fixed interface name.

    Raises:
        CanPrefixNameError: If the name starts with `can`.
    """
    if name.startswith(BANNED_NAME_PREFIX):
        raise CanPrefixNameError(
            f"fixed name {name!r} starts with {BANNED_NAME_PREFIX!r}; "
            "it races kernel canN assignment"
        )


def build_rule(
    name: str,
    dev_id: str | None,
    serial: str | None,
    port_path: str | None,
) -> UdevRule:
    """Build one two-axis rule, choosing serial or the port-path fallback.

    Serial is preferred; when it is absent the USB port path (`KERNELS==`) is the
    fallback adapter axis (`16` M-12, acceptance ④). Both an adapter axis and the
    `dev_id` channel axis must resolve, or the rule is refused.

    Args:
        name: Fixed interface name to bind.
        dev_id: `ATTR{dev_id}` channel discriminator, or None if unmeasured.
        serial: `ATTRS{serial}`, or None when the adapter reports none.
        port_path: `KERNELS==` port path, the fallback adapter discriminator.

    Returns:
        (UdevRule) The two-axis rule.

    Raises:
        CanPrefixNameError: If the name starts with `can`.
        MissingAxisError: If the channel axis or the adapter axis is unavailable.
    """
    assert_legal_name(name)
    if dev_id is None:
        raise MissingAxisError(
            f"rule for {name!r} has no channel axis: "
            "ATTR{dev_id} is required alongside the adapter axis"
        )
    if serial is not None:
        return UdevRule(name, AdapterAxisKind.SERIAL, serial, dev_id, ARPHRD_CAN_TYPE)
    if port_path is not None:
        return UdevRule(name, AdapterAxisKind.PORT_PATH, port_path, dev_id, ARPHRD_CAN_TYPE)
    raise MissingAxisError(
        f"rule for {name!r} has no adapter axis: "
        "neither ATTRS{serial} nor a KERNELS port path is available"
    )


def build_rule_for_interface(name: str, interface: UdevInterface) -> UdevRule:
    """Build a two-axis rule for a parsed interface.

    Args:
        name: Fixed interface name to bind to this physical channel.
        interface: Parsed `udevadm info` record.

    Returns:
        (UdevRule) The two-axis rule.

    Raises:
        CanPrefixNameError: If the name starts with `can`.
        MissingAxisError: If the interface lacks the channel or adapter axis.
    """
    return build_rule(name, interface.dev_id, interface.serial, interface.port_path)


def render_ruleset(rules: tuple[UdevRule, ...]) -> str:
    """Render a set of rules into an installable `.rules` file body.

    Args:
        rules: Rules to render, in file order.

    Returns:
        (str) The file body, one commented header line plus one line per rule.
    """
    header = (
        f"# /etc/udev/rules.d/{_RULES_FILENAME}\n"
        "# Fixed CAN names: adapter axis (serial or KERNELS port path) x channel axis (dev_id).\n"
    )
    return header + "\n".join(rule.render() for rule in rules) + "\n"
