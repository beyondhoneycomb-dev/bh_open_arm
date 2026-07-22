"""CTR-CAM@v1 — the name-based camera registry contract (a CTR-PRIM@v1 consumer).

The public surface: `CameraSpec` and `CameraRegistry` are the one camera schema
(`02b` §5.1 WP-3A-01: no fixed-slot contract); `make_arm_camera`/`make_top_level_camera`/
`make_sim_camera` build the three registration kinds; `camera_error` surfaces a
registered `OA-*` code through the shared `CTR-PRIM@v1` envelope. `checks`/`canonical`
hold the static guards and the frozen-body serializer.

The contract is DRAFT: `WP-3A-06` freezes `CTR-CAM@v1` (`06` §3.2), so this package
consumes `CTR-PRIM@v1` by import and restates no primitive.
"""

from __future__ import annotations

from contracts.camera_registry.canonical import canonical_document, canonical_json_text
from contracts.camera_registry.checks import (
    GeometryRedeclaration,
    check_no_primitive_redefinition,
    check_no_resolution_fps_redeclaration,
)
from contracts.camera_registry.schema import (
    CONSUMED_CONTRACT,
    CONTRACT_ID,
    SCHEMA_VERSION,
    SUPPORTED_CAPABILITIES,
    CameraRegistry,
    CameraRegistryError,
    CameraSpec,
    camera_error,
    make_arm_camera,
    make_sim_camera,
    make_top_level_camera,
    sim_satisfies,
)

__all__ = [
    "CONSUMED_CONTRACT",
    "CONTRACT_ID",
    "SCHEMA_VERSION",
    "SUPPORTED_CAPABILITIES",
    "CameraRegistry",
    "CameraRegistryError",
    "CameraSpec",
    "GeometryRedeclaration",
    "camera_error",
    "canonical_document",
    "canonical_json_text",
    "check_no_primitive_redefinition",
    "check_no_resolution_fps_redeclaration",
    "make_arm_camera",
    "make_sim_camera",
    "make_top_level_camera",
    "sim_satisfies",
]
