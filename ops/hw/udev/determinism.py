"""Reboot-determinism scaffold (`01` FR-SYS-008 acceptance ⑤⑥, SHAPE-MS verify-loop).

The whole reason udev fixing exists is that identical-VID/PID adapters get
non-deterministic `canN` numbers across boots (`16` M-12). The acceptance is empirical:
across ten reboots each fixed name must land on the *same physical channel* every time.

A physical channel is keyed by (adapter identity, `dev_id`) — never by the volatile
`canN` name. This module accumulates one observation per reboot and reports whether the
name-to-channel binding held. The reboot loop itself is the observation point (SHAPE-MS)
and needs real hardware — it is deferred. The evaluator is exercised here on synthetic
observation sets so a drift cannot pass silently; the reverify hook runs the identical
evaluator on real reboot captures.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ops.hw.udev.model import AdapterAxisKind, UdevInterface

# `01` FR-SYS-008 acceptance ⑤ — ten reboots, each a required observation point.
REQUIRED_REBOOT_CYCLES = 10


@dataclass(frozen=True)
class RebootObservation:
    """The fixed-name-to-physical-channel binding seen on one boot.

    Attributes:
        reboot_index: 0-based boot number.
        bindings: Fixed name to physical-channel key, as read this boot.
    """

    reboot_index: int
    bindings: Mapping[str, str]


@dataclass(frozen=True)
class DeterminismResult:
    """The verdict of a reboot-determinism run.

    Attributes:
        stable: True iff every required cycle bound every name to the same channel.
        cycles_seen: How many distinct reboot observations were supplied.
        required_cycles: The cycle count the acceptance demands.
        drifts: Human-readable descriptions of each binding that moved.
    """

    stable: bool
    cycles_seen: int
    required_cycles: int
    drifts: tuple[str, ...]


def physical_channel_key(interface: UdevInterface) -> str:
    """Return a boot-stable key for the physical channel an interface is.

    The key is (adapter identity, `dev_id`) — the two axes a rule binds — because
    that pair is invariant across boots while `canN` is not. An interface missing an
    axis yields an explicit `?` component rather than silently collapsing channels.

    Args:
        interface: A parsed interface.

    Returns:
        (str) The physical-channel key.
    """
    axis = interface.adapter_axis()
    axis_tag = axis.value if axis is not None else AdapterAxisKind.SERIAL.value
    return f"{axis_tag}:{interface.adapter_key() or '?'}/dev_id:{interface.dev_id or '?'}"


def evaluate_determinism(
    observations: tuple[RebootObservation, ...],
    required_cycles: int,
) -> DeterminismResult:
    """Judge whether fixed names bound to stable physical channels across reboots.

    The first observation is the reference binding; every later observation must
    reproduce it exactly. A name that binds a different channel, appears where the
    reference lacked it, or disappears, is a drift.

    Args:
        observations: One entry per reboot, in any order.
        required_cycles: Cycles the acceptance requires (typically ten).

    Returns:
        (DeterminismResult) The verdict, listing every drift found.
    """
    cycles_seen = len({observation.reboot_index for observation in observations})
    if not observations:
        return DeterminismResult(
            stable=False,
            cycles_seen=0,
            required_cycles=required_cycles,
            drifts=("no reboot observations supplied",),
        )

    ordered = sorted(observations, key=lambda observation: observation.reboot_index)
    reference = ordered[0].bindings
    drifts: list[str] = []
    for observation in ordered[1:]:
        names = set(reference) | set(observation.bindings)
        for name in sorted(names):
            want = reference.get(name)
            got = observation.bindings.get(name)
            if want != got:
                drifts.append(
                    f"reboot {observation.reboot_index}: {name} bound {got!r}, "
                    f"reference was {want!r}"
                )

    enough_cycles = cycles_seen >= required_cycles
    if not enough_cycles:
        drifts.append(f"only {cycles_seen} distinct reboot cycle(s); {required_cycles} required")

    return DeterminismResult(
        stable=not drifts,
        cycles_seen=cycles_seen,
        required_cycles=required_cycles,
        drifts=tuple(drifts),
    )
