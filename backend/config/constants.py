"""Named keys, paths and defaults for the runtime_config document (FR-GUI-004), and for the
service boundary `oa-serve` opens over it (FR-GUI-006).

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

from pathlib import Path
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
SUBOBJECT_PRESETS = "presets"
SUBOBJECT_END_EFFECTOR = "endEffector"
SUBOBJECT_CONTROL = "control"

FIELD_SIDEBAR_COLLAPSED = "sidebarCollapsed"
FIELD_DENSITY = "density"
FIELD_VIEW_PRESETS = "viewPresets"
FIELD_TOOL_ID = "toolId"
FIELD_TOOL_MASS_KG = "toolMassKg"
FIELD_CONTROL_TICK_HZ = "controlTickHz"

# The control loop's tick rate, and the band an operator may move it inside.
#
# 100 Hz is measured, not chosen: one batch send-then-collect over both channels and all 14
# fitted motors is 2.71 ms p50 / 3.16 ms max on this rig (300 cycles, torque-free), so the IO
# takes 27% of a 10 ms period and leaves the rest for the filter, IK and the trace. The sibling
# rig runs the same number for the same reason.
#
# The ceiling is where that budget stops being comfortable rather than where the bus stops
# keeping up: the same measurement achieves 369 Hz, but at 200 Hz the IO is 54% of the period and
# `bh_remy_openArm` D3 records that a single bus-owning thread stops being enough there — the
# next step is a thread per channel, which is a different design and not a setting. The floor is
# well under anything useful and exists so a typo cannot arm a timer that never fires.
CONTROL_TICK_HZ_DEFAULT = 100.0
CONTROL_TICK_HZ_MIN = 10.0
CONTROL_TICK_HZ_MAX = 200.0

# The tool-choice wire shape `GET /api/config/tools` emits. `toolId` is shared with the
# endEffector subobject on purpose: the id the GUI offers is the id it stores back.
FIELD_LABEL = "label"
FIELD_GRIPPER_MOTOR = "gripperMotor"

# The shell's layout-density vocabulary, mirrored from `frontend/src/config/schema.ts`. Declared
# as a type so an unlisted value is a validation failure rather than a string that reaches the
# browser and renders nothing.
LayoutDensity = Literal["comfortable", "compact"]

DENSITY_DEFAULT: LayoutDensity = "comfortable"
SIDEBAR_COLLAPSED_DEFAULT = False

# REST paths, served same-origin. The browser's copy of the base lives in
# `frontend/src/config/endpoints.ts` and nothing binds the two across the language boundary, so a
# change here is a change there.
CONFIG_ROUTE = "/api/config"
CONFIG_SUBOBJECT_ROUTE = "/api/config/{subobject}"
TOOLS_ROUTE = "/api/config/tools"

# The browser<->backend boundary `oa-serve` opens (13 §2.7, FR-GUI-006). One port carries the SPA
# bundle, the REST surface and the single WebSocket, which is what lets the browser hold exactly
# one origin and the air-gap CSP stay closed. The spec fixes the default and requires the port be
# configurable, so the number lives here and no call site spells it.
DEFAULT_HTTP_PORT = 8000

# Loopback until someone widens it. The operator's browser runs on the control host, so binding
# every interface would publish the control surface onto whatever network the host is plugged into
# without anyone having asked for that; `--host` keeps widening it a deliberate act.
DEFAULT_HTTP_HOST = "127.0.0.1"

# Where vite writes the built SPA (`frontend/vite.config.ts`: root `frontend/`, `build.outDir`
# `dist`), relative to the repository root. `.gitignore` excludes it, so a fresh clone carries no
# bundle until someone runs the frontend build — an absent bundle is a normal state, not a fault.
SPA_BUNDLE_DIRECTORY = Path("frontend") / "dist"

# The bundle entry, and the deep-link target every non-file route resolves to. Presence of the
# directory is NOT the test for a usable bundle: a leftover empty `dist/` satisfies that one and
# then answers every route with a 404 an operator cannot tell apart from a routing bug.
SPA_ENTRY_FILENAME = "index.html"

# The SPA mounts at the origin root, which is what `base: "./"` in the vite config resolves its
# assets against. A mount at `/` matches every path, so it is registered last — the REST routes
# and the WebSocket have to already be on the app before it goes on.
SPA_MOUNT_PATH = "/"
SPA_MOUNT_NAME = "spa"
