"""The runtime_config document, its four subobjects, and the lenient read that isolates them.

Two validation regimes live here and they are deliberately different (13 §「설정 영속(서버측)」,
CG-G-00d):

  * Strict, per subobject. `extra="forbid"`, closed vocabularies, and — for `endEffector` — the
    end-effector registry's own refusal. This is what a `PUT` runs, so a value the operator
    submits is either stored as sent or rejected with the reason.
  * Lenient, per document. `parse_document` validates each subobject on its own and replaces
    only the ones that fail. A corrupt `endEffector` must not cost the operator their `layout`,
    and — the direction that matters electrically — a corrupt `layout` must not silently change
    which tool the rig believes is fitted.

The read path's fallback is safe in one direction only, which is why the default tool is the one
with no motor on CAN id `0x08`: a defaulted `endEffector` under-polls the bus. Inventing a
gripper that is not there is what walks the controller to `ERROR-PASSIVE`, and that degrades the
seven joints that are present.

`toolId` resolves through `backend.endeffector.tool_by_id`, so the registry stays the single
list of tools; this module never enumerates them. `toolMassKg` is optional and stays optional —
it cannot be measured with torque off — but zero is refused, because an unweighed tool is null
rather than a number nobody measured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.config.constants import (
    CONTROL_TICK_HZ_DEFAULT,
    CONTROL_TICK_HZ_MAX,
    CONTROL_TICK_HZ_MIN,
    DENSITY_DEFAULT,
    FIELD_CONTROL_TICK_HZ,
    FIELD_DENSITY,
    FIELD_SIDEBAR_COLLAPSED,
    FIELD_TOOL_ID,
    FIELD_TOOL_MASS_KG,
    FIELD_VIEW_PRESETS,
    SIDEBAR_COLLAPSED_DEFAULT,
    SUBOBJECT_CONTROL,
    SUBOBJECT_END_EFFECTOR,
    SUBOBJECT_LAYOUT,
    SUBOBJECT_PRESETS,
    LayoutDensity,
)
from backend.endeffector import (
    DEFAULT_TOOL_ID,
    SIDE_LEFT,
    SIDE_RIGHT,
    EndEffectorError,
    EndEffectorProfile,
    RigEndEffectors,
    profile_for,
    tool_by_id,
)

# Wire shape: camelCase aliases, closed key set. `populate_by_name` admits the Python spelling
# too so callers inside the backend construct these without quoting wire names.
WIRE_MODEL_CONFIG = ConfigDict(extra="forbid", populate_by_name=True)


class LayoutConfig(BaseModel):
    """Shell chrome the operator arranged."""

    model_config = WIRE_MODEL_CONFIG

    sidebar_collapsed: bool = Field(
        default=SIDEBAR_COLLAPSED_DEFAULT, alias=FIELD_SIDEBAR_COLLAPSED
    )
    density: LayoutDensity = Field(default=DENSITY_DEFAULT, alias=FIELD_DENSITY)

    @field_validator("sidebar_collapsed", mode="before")
    @classmethod
    def _require_boolean(cls, value: object) -> object:
        """Refuse the values pydantic would otherwise read as a boolean (`"yes"`, `1`).

        `schema.ts` accepts only a real boolean. Coercing here would let the backend store a
        layout the browser then reads as malformed and replaces with defaults — the operator's
        arrangement would disappear with no refusal at either end.
        """
        if not isinstance(value, bool):
            raise ValueError(f"{FIELD_SIDEBAR_COLLAPSED} must be true or false, got {value!r}")
        return value


class PresetsConfig(BaseModel):
    """Per-screen view presets.

    Opaque to this module and to the shell: a screen's WP owns what its entries mean, and both
    ends only round-trip them. Validating their interiors here would put a second, always-stale
    copy of every screen's schema in the config canon.
    """

    model_config = WIRE_MODEL_CONFIG

    view_presets: dict[str, Any] = Field(default_factory=dict, alias=FIELD_VIEW_PRESETS)


class ControlConfig(BaseModel):
    """The control loop's tick rate, as the operator set it.

    One number rather than a set of periods, and that is the point. Every other cadence the loop
    runs — how often the state board is published, how many ticks a debounce counts, the grid a
    trajectory is sampled on — is a whole number of ticks, so retuning this moves all of them
    together. A build that also stored those separately would let the tick and the cadences
    derived from it disagree the moment one was edited, which is a defect that reads as jitter.

    It is persisted because it is a property of this rig rather than of a run: the number that
    holds on a machine is the one its measured IO leaves room for, and an operator who found it
    should not find it again next session.
    """

    model_config = WIRE_MODEL_CONFIG

    control_tick_hz: float = Field(
        default=CONTROL_TICK_HZ_DEFAULT,
        alias=FIELD_CONTROL_TICK_HZ,
        ge=CONTROL_TICK_HZ_MIN,
        le=CONTROL_TICK_HZ_MAX,
    )

    @field_validator("control_tick_hz", mode="before")
    @classmethod
    def _refuse_a_non_number(cls, value: object) -> object:
        """Refuse the values pydantic would read as a rate (`"100"`, `True`).

        A bool is checked first because `bool` is an `int` in Python, so `True` would otherwise
        store a 1 Hz tick — a control loop running once a second, arrived at by a type nobody
        noticed.
        """
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{FIELD_CONTROL_TICK_HZ} must be a number, got {value!r}")
        return value


class ArmEndEffectorConfig(BaseModel):
    """Which tool one arm carries, and what has been weighed about it."""

    model_config = WIRE_MODEL_CONFIG

    tool_id: str = Field(default=DEFAULT_TOOL_ID, alias=FIELD_TOOL_ID)
    tool_mass_kg: float | None = Field(default=None, alias=FIELD_TOOL_MASS_KG)

    @field_validator("tool_id")
    @classmethod
    def _refuse_unregistered_tool(cls, value: str) -> str:
        """Refuse an id the registry does not know, naming the ids it does.

        Re-raised as `ValueError` because pydantic converts only that into a validation error;
        an `EndEffectorError` escaping a validator would leave the route with no 4xx to return.
        """
        try:
            tool_by_id(value)
        except EndEffectorError as unknown:
            raise ValueError(str(unknown)) from unknown
        return value

    @field_validator("tool_mass_kg", mode="before")
    @classmethod
    def _refuse_unweighable_mass(cls, value: object) -> object:
        """Admit null, refuse zero and below, refuse anything that is not already a number.

        Runs before coercion because that is where the damage is. `bool` is an `int` subclass,
        so `true` would arrive as a 1 kg tool, and `"0.5"` would arrive as a measurement from a
        writer that never produced a number — both then subtracted by gravity compensation as if
        someone had weighed the tool, showing up as a standing collision-residual offset.
        """
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{FIELD_TOOL_MASS_KG} must be a number or null, got {value!r}")
        if value <= 0.0:
            raise ValueError(
                f"{FIELD_TOOL_MASS_KG} is {value}; a fitted tool has positive mass, and an "
                "unweighed one is null rather than zero"
            )
        return value

    def to_profile(self) -> EndEffectorProfile:
        """Return this arm's end-effector profile.

        Cannot fail: the tool id was resolved against the registry at validation time.
        """
        return profile_for(self.tool_id, self.tool_mass_kg)


class EndEffectorConfig(BaseModel):
    """What each arm carries — the operator's per-arm tool choice."""

    model_config = WIRE_MODEL_CONFIG

    left: ArmEndEffectorConfig = Field(default_factory=ArmEndEffectorConfig, alias=SIDE_LEFT)
    right: ArmEndEffectorConfig = Field(default_factory=ArmEndEffectorConfig, alias=SIDE_RIGHT)

    def to_rig(self) -> RigEndEffectors:
        """Return the rig record the CAN and payload paths consume."""
        return RigEndEffectors(left=self.left.to_profile(), right=self.right.to_profile())


class RuntimeConfigDocument(BaseModel):
    """The whole persisted document — what `GET /api/config` returns verbatim."""

    model_config = WIRE_MODEL_CONFIG

    layout: LayoutConfig = Field(default_factory=LayoutConfig, alias=SUBOBJECT_LAYOUT)
    presets: PresetsConfig = Field(default_factory=PresetsConfig, alias=SUBOBJECT_PRESETS)
    end_effector: EndEffectorConfig = Field(
        default_factory=EndEffectorConfig, alias=SUBOBJECT_END_EFFECTOR
    )
    control: ControlConfig = Field(default_factory=ControlConfig, alias=SUBOBJECT_CONTROL)

    def to_wire(self) -> dict[str, Any]:
        """Return the document as the camelCase object the browser client parses."""
        return self.model_dump(by_alias=True)


@dataclass(frozen=True)
class SubobjectSpec:
    """One subobject's three names: what the wire calls it, what the document calls it, and
    which model validates it.

    Attributes:
        key: The top-level wire key, and the `{subobject}` path segment of a PUT.
        field: The attribute on `RuntimeConfigDocument`.
        model: The strict model a PUT payload and a stored value are both validated against.
    """

    key: str
    field: str
    model: type[BaseModel]


SUBOBJECT_SPECS: tuple[SubobjectSpec, ...] = (
    SubobjectSpec(SUBOBJECT_LAYOUT, "layout", LayoutConfig),
    SubobjectSpec(SUBOBJECT_PRESETS, "presets", PresetsConfig),
    SubobjectSpec(SUBOBJECT_END_EFFECTOR, "end_effector", EndEffectorConfig),
    SubobjectSpec(SUBOBJECT_CONTROL, "control", ControlConfig),
)

SUBOBJECT_BY_KEY: dict[str, SubobjectSpec] = {spec.key: spec for spec in SUBOBJECT_SPECS}
SUBOBJECT_KEYS: tuple[str, ...] = tuple(spec.key for spec in SUBOBJECT_SPECS)


def default_document() -> RuntimeConfigDocument:
    """The document before an operator has chosen anything — both arms on the no-`0x08` tool."""
    return RuntimeConfigDocument()


@dataclass(frozen=True)
class ParsedDocument:
    """A document read with blast-radius isolation, and which subobjects paid for it.

    Attributes:
        document: Every subobject that validated, plus defaults in place of every one that did
            not.
        defaulted: The wire keys that were replaced, in document order. Empty when the source
            validated whole or carried nothing at all. A non-empty `endEffector` entry means the
            rig is being reported on the default tool rather than on a stored answer.
    """

    document: RuntimeConfigDocument
    defaulted: tuple[str, ...]


def parse_document(raw: object) -> ParsedDocument:
    """Validate a raw config object subobject by subobject, defaulting only what fails.

    An absent subobject is not a failure — nothing was stored, so the default stands and nothing
    is reported. A top-level key outside `SUBOBJECT_KEYS` is dropped rather than refused: the key
    set is closed, and refusing the whole document over one stray key would default all four
    subobjects, which is the blast radius CG-G-00d exists to prevent.

    Args:
        raw: The parsed JSON body, of any shape.

    Returns:
        (ParsedDocument) The document, and the keys that fell back to defaults.
    """
    if not isinstance(raw, dict):
        return ParsedDocument(document=default_document(), defaulted=SUBOBJECT_KEYS)

    document = default_document()
    defaulted: list[str] = []
    for spec in SUBOBJECT_SPECS:
        if spec.key not in raw:
            continue
        try:
            validated = spec.model.model_validate(raw[spec.key])
        except ValidationError:
            defaulted.append(spec.key)
            continue
        document = document.model_copy(update={spec.field: validated})
    return ParsedDocument(document=document, defaulted=tuple(defaulted))


def rig_from_document(document: RuntimeConfigDocument) -> RigEndEffectors:
    """Return what each arm carries according to this document."""
    return document.end_effector.to_rig()


__all__ = [
    "SUBOBJECT_BY_KEY",
    "SUBOBJECT_KEYS",
    "SUBOBJECT_SPECS",
    "ArmEndEffectorConfig",
    "EndEffectorConfig",
    "LayoutConfig",
    "ParsedDocument",
    "PresetsConfig",
    "RuntimeConfigDocument",
    "SubobjectSpec",
    "default_document",
    "parse_document",
    "rig_from_document",
]
