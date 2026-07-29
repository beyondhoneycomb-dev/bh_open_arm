"""Named keys, paths and defaults for the runtime_config document (FR-GUI-004).

The wire is camelCase because the browser client already reads it that way
(`frontend/src/config/schema.ts`); Python field names stay snake_case and carry the wire name
as a pydantic alias. Every key appears in at least two places — the model that declares it and
the reader or route that names it — so each is a constant here rather than a literal repeated
at both ends, where a typo would silently drop an operator's saved value.

The side names and the default tool id are NOT declared here. `backend.endeffector` owns them;
re-typing either would put a second answer to "which tool is fitted" in the tree, and that
question decides whether CAN id `0x08` is polled.
"""

from __future__ import annotations

from typing import Literal

# The document file name under the config directory. The whole file is the wire document: what
# `GET /api/config` returns is what sits on disk, so a hand-edit is readable with the same rules
# the API applies.
CONFIG_FILENAME = "runtime_config.json"

# The XDG application directory. Product-wide rather than per-package: an operator looking for
# "the GUI settings" opens one folder, not one per backend module.
APP_DIRECTORY = "openarm"

XDG_CONFIG_HOME_VAR = "XDG_CONFIG_HOME"
# What XDG specifies when $XDG_CONFIG_HOME is unset or not absolute.
XDG_CONFIG_HOME_FALLBACK = ".config"

# The closed set of top-level subobject keys, and the `{subobject}` path segment a PUT names.
SUBOBJECT_LAYOUT = "layout"
SUBOBJECT_THEME = "theme"
SUBOBJECT_PRESETS = "presets"
SUBOBJECT_END_EFFECTOR = "endEffector"

FIELD_SIDEBAR_COLLAPSED = "sidebarCollapsed"
FIELD_DENSITY = "density"
FIELD_MODE = "mode"
FIELD_VIEW_PRESETS = "viewPresets"
FIELD_TOOL_ID = "toolId"
FIELD_TOOL_MASS_KG = "toolMassKg"

# The tool-choice wire shape `GET /api/config/tools` emits. `toolId` is shared with the
# endEffector subobject on purpose: the id the GUI offers is the id it stores back.
FIELD_LABEL = "label"
FIELD_GRIPPER_MOTOR = "gripperMotor"

# The two shell appearance vocabularies, mirrored from `frontend/src/config/schema.ts`. Declared
# as types so an unlisted value is a validation failure rather than a string that reaches the
# browser and renders nothing.
LayoutDensity = Literal["comfortable", "compact"]
ThemeMode = Literal["light", "dark", "system"]

DENSITY_DEFAULT: LayoutDensity = "comfortable"
THEME_MODE_DEFAULT: ThemeMode = "system"
SIDEBAR_COLLAPSED_DEFAULT = False

# REST paths, served same-origin. The browser's copy of the base lives in
# `frontend/src/config/endpoints.ts` and nothing binds the two across the language boundary, so a
# change here is a change there.
CONFIG_ROUTE = "/api/config"
CONFIG_SUBOBJECT_ROUTE = "/api/config/{subobject}"
TOOLS_ROUTE = "/api/config/tools"
