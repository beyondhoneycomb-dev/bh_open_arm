"""The `ATTR{dev_id}` / `ATTRS{serial}` measurement table (`01` FR-SYS-008, acceptance ②③).

FR-SYS-008 makes two empirical claims the plan requires *verified*, not assumed:

- ② one adapter's two channels share one `ATTRS{serial}` — serial is per-adapter,
  so it cannot alone tell the channels apart.
- ③ `ATTR{dev_id}` differs between those two channels — so it is what does.

This module folds a set of parsed interfaces into the measurement table and answers
both claims from it. The *computation* runs here on synthetic four-entry fixtures; the
*real* four-entry measurement needs two physical adapters and is deferred (the reverify
hook re-runs this same computation on a real capture the moment one is supplied).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ops.hw.udev.model import AdapterAxisKind, UdevInterface


@dataclass(frozen=True)
class ChannelEntry:
    """One channel's row in the measurement table.

    Attributes:
        interface: Kernel name at capture time (bookkeeping only).
        adapter_key: Serial when present, else port path — the adapter identity.
        adapter_axis: Which axis `adapter_key` came from.
        dev_id: The channel discriminator, or None if the capture lacked it.
    """

    interface: str
    adapter_key: str | None
    adapter_axis: AdapterAxisKind | None
    dev_id: str | None


@dataclass(frozen=True)
class MeasurementTable:
    """The full four-entry (two adapters x two channels) measurement.

    Attributes:
        entries: One `ChannelEntry` per interface, in input order.
    """

    entries: tuple[ChannelEntry, ...]

    def by_adapter(self) -> dict[str, list[ChannelEntry]]:
        """Group entries by adapter identity.

        Returns:
            (dict[str, list[ChannelEntry]]) Adapter key to its channel rows;
            entries with no adapter key are omitted (they pin to no adapter).
        """
        groups: dict[str, list[ChannelEntry]] = defaultdict(list)
        for entry in self.entries:
            if entry.adapter_key is not None:
                groups[entry.adapter_key].append(entry)
        return dict(groups)


def build_measurement_table(interfaces: tuple[UdevInterface, ...]) -> MeasurementTable:
    """Fold parsed interfaces into the measurement table.

    Args:
        interfaces: Parsed `udevadm info` records.

    Returns:
        (MeasurementTable) One entry per interface.
    """
    entries = tuple(
        ChannelEntry(
            interface=interface.interface,
            adapter_key=interface.adapter_key(),
            adapter_axis=interface.adapter_axis(),
            dev_id=interface.dev_id,
        )
        for interface in interfaces
    )
    return MeasurementTable(entries=entries)


# How many channels of one adapter a capture must hold before it can show that `dev_id`
# separates them. One channel exhibits no separation: nothing is absent and nothing collides.
_CHANNELS_NEEDED_TO_SHOW_SEPARATION = 2


def serial_shared_per_adapter(table: MeasurementTable) -> bool:
    """Answer acceptance ②: is `ATTRS{serial}` shared per adapter, not per channel?

    True iff at least one serial-keyed adapter carries more than one channel and
    every serial-keyed adapter's channels are distinct (different `dev_id`). A serial
    that appeared on only one channel, or that collided across genuinely different
    channels, would contradict the per-adapter-sharing claim.

    Args:
        table: The measurement table.

    Returns:
        (bool) Whether the per-adapter-sharing claim holds in this measurement.
    """
    serial_groups = [
        entries
        for entries in table.by_adapter().values()
        if entries and entries[0].adapter_axis is AdapterAxisKind.SERIAL
    ]
    if not serial_groups:
        return False
    saw_shared = False
    for entries in serial_groups:
        dev_ids = [entry.dev_id for entry in entries]
        if len(entries) > 1:
            saw_shared = True
            if len(set(dev_ids)) != len(dev_ids):
                return False
    return saw_shared


def dev_id_distinguishes_channels(table: MeasurementTable) -> bool:
    """Answer acceptance ③: does `ATTR{dev_id}` distinguish channels within an adapter?

    True iff every adapter carries more than one channel and no adapter has two channels
    reporting the same (or absent) `dev_id`.

    The multi-channel requirement is the acceptance rather than a precondition of it. What ③
    claims is that `dev_id` *separates* the channels of an adapter, and a capture holding one
    channel of one adapter exhibits no separation to judge: it has no absent id and no
    collision, so a bare uniqueness test passes it vacuously. `serial_shared_per_adapter`
    guards the mirrored claim with `saw_shared` for the same reason.

    Counting interfaces would not do it. Two dumps from two different adapters, each holding
    one channel and both reading `dev_id` 0x0, is two interfaces and still no adapter whose
    channels were separated — so the requirement is per adapter, not per capture.

    Args:
        table: The measurement table.

    Returns:
        (bool) Whether `dev_id` separates the channels of every adapter.
    """
    groups = table.by_adapter()
    if not groups:
        return False
    for entries in groups.values():
        if len(entries) < _CHANNELS_NEEDED_TO_SHOW_SEPARATION:
            return False
        dev_ids = [entry.dev_id for entry in entries]
        if any(dev_id is None for dev_id in dev_ids):
            return False
        if len(set(dev_ids)) != len(dev_ids):
            return False
    return True
