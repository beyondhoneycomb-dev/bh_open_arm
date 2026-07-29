"""The runtime_config canon and the REST surface the GUI reads it through (FR-GUI-004).

Four subobjects — `layout`, `theme`, `presets`, `endEffector` — persisted as one JSON document
under the XDG config directory, written atomically, and read with per-subobject blast-radius
isolation: a malformed subobject falls back to its defaults and the other three are preserved
(CG-G-00d). `frontend/src/config/schema.ts` implements the mirror image for the browser copy.

`endEffector` is the subobject with a consequence outside the screen. It records which tool each
arm carries, and `backend.endeffector` — not this package — owns what the tool ids are and what
follows from them. A stored id resolves through `tool_by_id`, so an unregistered one is refused
with the known ids named rather than defaulted: the answer decides whether CAN id `0x08` gets
polled, and polling an absent motor walks the controller to `ERROR-PASSIVE` and degrades the
seven joints that are present.
"""

from backend.config.api import create_app, tool_choice
from backend.config.constants import (
    APP_DIRECTORY,
    CONFIG_FILENAME,
    CONFIG_ROUTE,
    CONFIG_SUBOBJECT_ROUTE,
    SUBOBJECT_END_EFFECTOR,
    SUBOBJECT_LAYOUT,
    SUBOBJECT_PRESETS,
    SUBOBJECT_THEME,
    TOOLS_ROUTE,
)
from backend.config.model import (
    SUBOBJECT_KEYS,
    ArmEndEffectorConfig,
    EndEffectorConfig,
    LayoutConfig,
    ParsedDocument,
    PresetsConfig,
    RuntimeConfigDocument,
    ThemeConfig,
    default_document,
    parse_document,
    rig_from_document,
)
from backend.config.store import (
    RuntimeConfigStore,
    UnknownSubobjectError,
    config_path_for,
    default_config_directory,
    default_store,
    load_document,
    save_document_atomic,
)

__all__ = [
    "APP_DIRECTORY",
    "CONFIG_FILENAME",
    "CONFIG_ROUTE",
    "CONFIG_SUBOBJECT_ROUTE",
    "SUBOBJECT_END_EFFECTOR",
    "SUBOBJECT_KEYS",
    "SUBOBJECT_LAYOUT",
    "SUBOBJECT_PRESETS",
    "SUBOBJECT_THEME",
    "TOOLS_ROUTE",
    "ArmEndEffectorConfig",
    "EndEffectorConfig",
    "LayoutConfig",
    "ParsedDocument",
    "PresetsConfig",
    "RuntimeConfigDocument",
    "RuntimeConfigStore",
    "ThemeConfig",
    "UnknownSubobjectError",
    "config_path_for",
    "create_app",
    "default_config_directory",
    "default_document",
    "default_store",
    "load_document",
    "parse_document",
    "rig_from_document",
    "save_document_atomic",
    "tool_choice",
]
