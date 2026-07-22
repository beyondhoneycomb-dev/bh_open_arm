"""CTR-CAM@v1 — the name-based camera registry, a consumer of CTR-PRIM@v1.

`02b` §5.1/§5.2 WP-3A-01 fixes one camera schema and forbids a fixed-slot
contract: the set of cameras is a name-keyed registry, not a fixed list of slots.
This module is that registry. It **consumes** three CTR-PRIM primitives by import
and restates none of them (`02b` §5.0b, the single-definition rule the
`check_no_primitive_redefinition` scan enforces):

* the camera identifier — `CameraSlotKey`, `arm_slot`, `sim_slot` and the slot's
  own join derivations. The slot key is the one identifier that round-trips across
  CAM/CAP/WS/REC, so a camera keeps one name at every surface.
* the frame-type tag — `FrameType`, with `REQUIRED_FRAME_TYPE` (RGB) the
  capability floor and `OPTIONAL_FRAME_TYPES` (depth) the optional extension. This
  contract states the required/optional split; it does not redefine the enum.
* the error envelope — `ErrorEnvelope`, the one shape a camera surface reports a
  registered `OA-*` code in (`camera_error`).

What this contract adds over the primitives (`02b` §5.2 WP-3A-01):

1. required-vs-optional capability — RGB required, depth optional, and simulation
   matches when it meets the required subset, never "exactly N identical streams".
2. per-arm vs top-level registration — an arm camera's key carries `left_`/`right_`
   (auto-attached by `arm_slot`); a top-level camera carries no arm prefix.
3. dataset-key derivation with resolution and fps declared in exactly one place —
   the `CameraSpec` dict. No layer restates `width`/`height`/`fps`; the dataset
   keys are derived from the slot alone (`check_no_resolution_fps_redeclaration`).
4. name-collision rejection before save, and a separate simulation namespace so a
   sim scene camera can never collide with, or be joined to, a real slot.

Status is DRAFT: `WP-3A-06` freezes `CTR-CAM@v1` sequentially with the other four
consumers, so this module does not append to the freeze ledger. The frozen body
is the language-neutral `schema.json` (`canonical.canonical_json_text`), declared
`CONTRACT_FROZEN` in the WP-3A-01 registry row and generated at freeze time.

Serves `FR-CAM-001`/`006`/`070`/`081`/`088`, `FR-REC-013`, `FR-SIM-019`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from contracts.prim import (
    OPTIONAL_FRAME_TYPES,
    REQUIRED_FRAME_TYPE,
    CameraSlotKey,
    ErrorCode,
    ErrorEnvelope,
    FrameType,
    arm_slot,
    error_envelope,
    sim_slot,
)

# The contract id this module is the DRAFT body of. Consumers and the freeze
# check key on this exact string, so it is named once.
CONTRACT_ID = "CTR-CAM@v1"

# The generation. A change to the schema is `CTR-CAM@v2`, never an in-place edit
# (`06` §4.3); the value is the same generation `CTR-PRIM@v1` consumes.
SCHEMA_VERSION = 1

# The upstream frozen contract every camera identifier, frame type and error
# envelope is drawn from. Named so a bump of it propagates staleness here (`CR-2`).
CONSUMED_CONTRACT = "CTR-PRIM@v1"

# The full capability vocabulary: the required floor plus the optional extensions.
# Both halves come from `CTR-PRIM@v1`; this contract only names their union so a
# capability outside it (a frame type CAM never defined) is rejected on sight.
SUPPORTED_CAPABILITIES = frozenset({REQUIRED_FRAME_TYPE, *OPTIONAL_FRAME_TYPES})


class CameraRegistryError(ValueError):
    """Raised when a registration violates the `CTR-CAM@v1` contract.

    The refusals this contract owns — a missing RGB capability, an unconfigured
    resolution at collection start, a duplicate slot name, an unknown capability —
    are contract violations, not runtime `OA-*` conditions, so they raise here
    rather than being wrapped in an `ErrorEnvelope`. `camera_error` is the separate
    path for surfacing a registered runtime code.
    """


@dataclass(frozen=True)
class CameraSpec:
    """One registered camera: its slot identity, capabilities and stream geometry.

    This dataclass is the single place `width`, `height` and `fps` are declared.
    No other layer restates them (`02b` §5.2 WP-3A-01 ①); dataset keys and every
    downstream surface derive from the slot alone. The three geometry fields are
    optional so a camera can be *registered* before it is *configured*; a `None`
    on any of them blocks collection start (`02b` §5.2 WP-3A-01 ②), it does not
    silently default.

    Attributes:
        slot: The camera identifier, a `CTR-PRIM@v1` `CameraSlotKey`.
        capabilities: The frame types this camera provides; must include the
            required floor (`REQUIRED_FRAME_TYPE`).
        width: Frame width in pixels, or None when not yet configured.
        height: Frame height in pixels, or None when not yet configured.
        fps: Frames per second, or None when not yet configured.
    """

    slot: CameraSlotKey
    capabilities: frozenset[FrameType]
    width: int | None
    height: int | None
    fps: int | None

    def __post_init__(self) -> None:
        """Reject a capability set that breaks the required/optional split."""
        unknown = self.capabilities - SUPPORTED_CAPABILITIES
        if unknown:
            offered = sorted(frame_type.value for frame_type in unknown)
            vocabulary = sorted(frame_type.value for frame_type in SUPPORTED_CAPABILITIES)
            raise CameraRegistryError(
                f"camera {self.slot.value!r} declares capabilities {offered} "
                f"outside {CONTRACT_ID}'s vocabulary {vocabulary}"
            )
        if REQUIRED_FRAME_TYPE not in self.capabilities:
            raise CameraRegistryError(
                f"camera {self.slot.value!r} is missing the required capability "
                f"{REQUIRED_FRAME_TYPE.value}; {CONTRACT_ID} requires it of every camera"
            )

    @property
    def is_configured(self) -> bool:
        """Whether resolution and fps are all specified, so collection may start."""
        return self.width is not None and self.height is not None and self.fps is not None

    @property
    def has_depth(self) -> bool:
        """Whether this camera provides the optional depth capability."""
        return FrameType.DEPTH in self.capabilities

    @property
    def arm(self) -> str | None:
        """The arm this camera is bound to, or None for a top-level camera."""
        return self.slot.arm

    @property
    def is_sim(self) -> bool:
        """Whether this camera is a simulation scene camera in the sim namespace."""
        return self.slot.is_sim

    def configured(self, width: int, height: int, fps: int) -> CameraSpec:
        """Return a copy with resolution and fps set, ready for collection.

        Args:
            width: Frame width in pixels.
            height: Frame height in pixels.
            fps: Frames per second.

        Returns:
            (CameraSpec) The same camera with its geometry specified.
        """
        return replace(self, width=width, height=height, fps=fps)

    def dataset_image_key(self) -> str:
        """The LeRobot RGB feature key for this camera (`observation.images.<slot>`).

        Derived from the slot alone through the `CTR-PRIM@v1` derivation, so the
        key carries no resolution or fps (`02b` §5.2 WP-3A-01 ①).
        """
        return self.slot.image_key()

    def dataset_depth_key(self) -> str | None:
        """The depth feature key (`observation.images.<slot>_depth`), or None.

        Returns None when this camera has no depth capability, so a consumer never
        derives a depth key for an RGB-only camera.
        """
        return self.slot.depth_key() if self.has_depth else None

    def ui_arm_prefix_note(self) -> str | None:
        """The note a UI shows about an auto-attached arm prefix, or None.

        Per-arm registration auto-attaches `left_`/`right_` to the slot key
        (`02b` §5.2 WP-3A-01 ③); a UI must make that visible so the operator sees
        the registered key, not the bare base name they typed.
        """
        if self.arm is None:
            return None
        return (
            f"registered as {self.slot.value!r}: "
            f"the {self.arm}_ arm prefix is attached automatically"
        )


def make_arm_camera(side: str, base: str, capabilities: frozenset[FrameType]) -> CameraSpec:
    """Build a per-arm camera whose slot key carries the arm prefix.

    The prefix is attached by the `CTR-PRIM@v1` `arm_slot` derivation, never by a
    string this contract assembles, so the arm a frame belongs to survives every
    join. Geometry is left unspecified; the camera is registered before it is
    configured.

    Args:
        side: `"left"` or `"right"`.
        base: The bare camera name, without any arm prefix.
        capabilities: The frame types the camera provides (must include RGB).

    Returns:
        (CameraSpec) An unconfigured per-arm camera.
    """
    return CameraSpec(
        slot=arm_slot(side, base), capabilities=capabilities, width=None, height=None, fps=None
    )


def make_top_level_camera(name: str, capabilities: frozenset[FrameType]) -> CameraSpec:
    """Build a top-level camera whose slot key carries no arm prefix.

    Args:
        name: The camera name; must be a valid bare slot key with no arm or sim
            prefix (a top-level camera belongs to neither namespace).
        capabilities: The frame types the camera provides (must include RGB).

    Returns:
        (CameraSpec) An unconfigured top-level camera.

    Raises:
        CameraRegistryError: If the name already carries an arm or sim prefix, so
            it is not a top-level identity.
    """
    slot = CameraSlotKey(name)
    if slot.arm is not None or slot.is_sim:
        raise CameraRegistryError(
            f"{name!r} is namespaced ({slot.value!r}); a top-level camera carries no arm/sim prefix"
        )
    return CameraSpec(slot=slot, capabilities=capabilities, width=None, height=None, fps=None)


def make_sim_camera(base: str, capabilities: frozenset[FrameType]) -> CameraSpec:
    """Build a simulation scene camera in the `CTR-PRIM@v1` sim namespace.

    Args:
        base: The bare scene-camera name, without any namespace prefix.
        capabilities: The frame types the camera provides (must include RGB).

    Returns:
        (CameraSpec) An unconfigured sim scene camera whose slot cannot collide
            with a real slot (`02b` §5.2 WP-3A-01 ⑤).
    """
    return CameraSpec(
        slot=sim_slot(base), capabilities=capabilities, width=None, height=None, fps=None
    )


def sim_satisfies(required: CameraSpec, candidate: CameraSpec) -> bool:
    """Whether a sim camera meets a real camera's required capability subset.

    `02b` §5.2 WP-3A-01 states simulation is conformant when it covers the required
    capability *subset*, not when it reproduces the exact stream set. So a sim
    camera providing at least the required camera's capabilities conforms, even if
    the real camera additionally offers optional depth the sim omits — provided the
    required floor (RGB) is met by both.

    Args:
        required: The real camera whose required capabilities must be covered.
        candidate: The sim camera offered as a stand-in.

    Returns:
        (bool) True when the candidate covers the required floor of both.
    """
    floor = (required.capabilities & {REQUIRED_FRAME_TYPE}) | {REQUIRED_FRAME_TYPE}
    return floor <= candidate.capabilities


def camera_error(code: ErrorCode, reason: str) -> ErrorEnvelope:
    """Surface a registered camera `OA-*` code through the shared error envelope.

    The envelope is the `CTR-PRIM@v1` primitive; this is the single path a camera
    surface reports a registered runtime code, so an `OA-CAM-*` code reads
    identically here and in WS/REC (`02b` §5.0b row 6). It wraps a registered code
    only — an unregistered code is refused by the envelope itself.

    Args:
        code: A registered `CTR-ERR@v1` code (e.g. `REGISTRY.get(codes.OA_CAM_001)`).
        reason: The human-readable reason to attach.

    Returns:
        (ErrorEnvelope) The envelope carrying the code, reason and severity.
    """
    return error_envelope(code, reason)


@dataclass
class CameraRegistry:
    """A name-keyed set of registered cameras — the one camera schema, not a slot list.

    There is no fixed-slot contract (`02b` §5.2 WP-3A-01): cameras are registered by
    name into this registry, collisions are rejected before save, and a simulation
    scene camera lives in a namespace that cannot collide with a real slot because
    its key is `sim_`-prefixed. Collection start is blocked while any registered
    camera is unconfigured.

    Ownership: a single registry instance is the authority for one collection
    session's cameras; it is mutated only through `register`.

    Attributes:
        cameras: Registered cameras keyed by their slot-key string.
    """

    cameras: dict[str, CameraSpec] = field(default_factory=dict)

    def register(self, spec: CameraSpec) -> None:
        """Register a camera, rejecting a slot-name collision before it is stored.

        A real and a sim camera that share a base name do not collide: their slot
        keys differ (`front` vs `sim_front`), so both register. Two cameras with
        the same slot key do collide, and the second is refused (`02b` §5.2
        WP-3A-01 ④) — the store is left unchanged.

        Args:
            spec: The camera to register.

        Raises:
            CameraRegistryError: If a camera with the same slot key is registered.
        """
        key = spec.slot.value
        if key in self.cameras:
            raise CameraRegistryError(
                f"slot {key!r} is already registered; a camera name must be unique before save"
            )
        self.cameras[key] = spec

    def get(self, slot: CameraSlotKey) -> CameraSpec:
        """Return the registered camera for a slot key.

        Args:
            slot: The slot key to look up.

        Returns:
            (CameraSpec) The registered camera.

        Raises:
            CameraRegistryError: If no camera is registered under that slot.
        """
        try:
            return self.cameras[slot.value]
        except KeyError as missing:
            raise CameraRegistryError(
                f"no camera registered under slot {slot.value!r}"
            ) from missing

    def real_cameras(self) -> tuple[CameraSpec, ...]:
        """Return the registered real (non-simulation) cameras, in key order."""
        return tuple(spec for _, spec in sorted(self.cameras.items()) if not spec.is_sim)

    def sim_cameras(self) -> tuple[CameraSpec, ...]:
        """Return the registered simulation scene cameras, in key order."""
        return tuple(spec for _, spec in sorted(self.cameras.items()) if spec.is_sim)

    def unconfigured(self) -> tuple[CameraSpec, ...]:
        """Return the registered cameras still missing resolution or fps, in key order."""
        return tuple(spec for _, spec in sorted(self.cameras.items()) if not spec.is_configured)

    def assert_collection_startable(self) -> None:
        """Block collection start while any registered camera is unconfigured.

        `02b` §5.2 WP-3A-01 ② requires that unspecified `width`/`height`/`fps`
        block the start of collection rather than adopt a default. This is that
        gate: it raises when any camera lacks its geometry, naming the offenders.

        Raises:
            CameraRegistryError: If any registered camera is not fully configured.
        """
        blocking = [spec.slot.value for spec in self.unconfigured()]
        if blocking:
            raise CameraRegistryError(
                f"collection start blocked: {blocking} have unspecified width/height/fps; "
                f"{CONTRACT_ID} requires all three before collection begins"
            )
