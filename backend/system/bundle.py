"""What a diagnostic bundle generated right now would actually contain.

`14` FR-OPS-023 lists ten items and the browser holds that list
(`frontend/src/screens/S-13/diagnosticBundle.ts`), computing what is missing from what this
manifest claims. So the claim has to be true: an id listed here is one the report beside it
already carries, not one a future generator is expected to produce.

Two are claimed today — the system information and the bound port map — because this very
report holds both. The other eight name subsystems that are built and not yet wired to a
producer, and the screen showing them as missing is the honest reading of that.

The video and PII choices are the operator's (`FR-OPS-023`), so both default to excluded. A
bundle that shipped either without being asked is the failure that clause exists to prevent.
"""

from __future__ import annotations

from typing import Any

INCLUDED_ITEM_IDS_FIELD = "includedItemIds"
INCLUDE_VIDEO_FIELD = "includeVideo"
INCLUDE_PII_FIELD = "includePii"

# The two ids this report backs with data it already produced. Both names are the browser's
# (`REQUIRED_DIAGNOSTIC_ITEMS`), which owns the list `14` FR-OPS-023 declares.
SYSTEM_INFO_ITEM = "system_info"
BOUND_PORT_MAP_ITEM = "bound_port_map"

PRODUCIBLE_ITEM_IDS: tuple[str, ...] = (SYSTEM_INFO_ITEM, BOUND_PORT_MAP_ITEM)


def bundle_manifest() -> dict[str, Any]:
    """The manifest of a bundle built from what this process can produce.

    Returns:
        (dict) The manifest, in the browser's `BundleManifest` shape.
    """
    return {
        INCLUDED_ITEM_IDS_FIELD: list(PRODUCIBLE_ITEM_IDS),
        INCLUDE_VIDEO_FIELD: False,
        INCLUDE_PII_FIELD: False,
    }


__all__ = [
    "BOUND_PORT_MAP_ITEM",
    "INCLUDED_ITEM_IDS_FIELD",
    "INCLUDE_PII_FIELD",
    "INCLUDE_VIDEO_FIELD",
    "PRODUCIBLE_ITEM_IDS",
    "SYSTEM_INFO_ITEM",
    "bundle_manifest",
]
