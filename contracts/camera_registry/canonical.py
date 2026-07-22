"""The language-neutral frozen body of CTR-CAM@v1 — `schema.json`'s content.

`WP-3A-01` leaves `CTR-CAM@v1` DRAFT: it does not append to the freeze ledger, so
the frozen mirror `contracts/camera_registry/schema.json` is not committed while
the parallel consumers are still landing (`02b` §5.0b, the chained-ledger race).
`WP-3A-06` generates it from `canonical_json_text` and freezes it sequentially
after the other four. Keeping the mirror out of the tree until then is what keeps
CI-09 green while the contract is DRAFT — a `CONTRACT_FROZEN` glob with content but
no locked hash is itself a CI-09 finding.

The document is derived, not hand-authored, so the frozen hash is a deterministic
function of this contract's constants. It restates no primitive: the slot-key
grammar, the frame-type channels and the error grammar live in `CTR-PRIM@v1` and
are referenced here by their contract id, not copied.
"""

from __future__ import annotations

import json
from typing import Any

from contracts.camera_registry.schema import CONTRACT_ID, SCHEMA_VERSION
from contracts.prim import (
    CAMERA_SLOT_KEY_PATTERN,
    OPTIONAL_FRAME_TYPES,
    REQUIRED_FRAME_TYPE,
    SIM_NAMESPACE_PREFIX,
)
from contracts.prim import CONTRACT_ID as PRIM_CONTRACT_ID


def canonical_document() -> dict[str, Any]:
    """Build the frozen contract document as a plain, ordered mapping.

    Returns:
        (dict[str, Any]) The `CTR-CAM@v1` schema, referencing `CTR-PRIM@v1` for the
            primitives it consumes rather than restating them.
    """
    return {
        "contract": CONTRACT_ID,
        "version": SCHEMA_VERSION,
        "consumes": PRIM_CONTRACT_ID,
        "model": "name-keyed registry; no fixed-slot contract",
        "identifier": {
            "source": PRIM_CONTRACT_ID,
            "slot_key_pattern": CAMERA_SLOT_KEY_PATTERN.pattern,
            "sim_namespace_prefix": SIM_NAMESPACE_PREFIX,
        },
        "capabilities": {
            "required": [REQUIRED_FRAME_TYPE.value],
            "optional": [frame_type.value for frame_type in OPTIONAL_FRAME_TYPES],
            "simulation_conformance": "required-subset; not exact-stream-match",
        },
        "geometry": {
            "declared_in": "camera spec only",
            "fields": ["width", "height", "fps"],
            "unspecified_blocks_collection_start": True,
            "restated_elsewhere": False,
        },
        "dataset_keys": {
            "rgb": "observation.images.<slot>",
            "depth": "observation.images.<slot>_depth",
            "derived_from": "slot key; carries no width/height/fps",
        },
        "registration": {
            "arm_prefix_auto_attached": True,
            "slot_name_collision": "rejected before save",
            "sim_namespace_isolated": True,
        },
    }


def canonical_json_text() -> str:
    """Serialize the frozen document to deterministic JSON bytes-as-text.

    Sorted keys and a fixed indent make the output byte-stable, so the hash
    `WP-3A-06` locks is a function of the contract alone, not of dict ordering.

    Returns:
        (str) The canonical `schema.json` content, newline-terminated.
    """
    return json.dumps(canonical_document(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
