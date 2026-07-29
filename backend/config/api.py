"""The REST surface over runtime_config — three routes, no server (FR-GUI-004, 13 §2.7).

`create_app` builds the ASGI application and binds nothing; a socket is opened by whoever hosts
it, which is what lets the routes be driven by a test client in-process. No module-level app
exists on purpose — importing this module must not resolve an XDG path or touch a disk the
importer did not ask about.

`GET /api/config/tools` is the reason the GUI carries no tool list of its own. It maps
`backend.endeffector.registered_tools()` onto the wire, so a tool added as a registry row shows
up as a choice with nothing here re-opened; the field the operator's decision actually turns on
is `gripperMotor`, which says whether CAN id `0x08` is a motor on an arm carrying that tool.

Every refusal on `PUT` is a 4xx carrying the reason and the admissible values. Silently
correcting an `endEffector` payload is the one outcome the surface must never produce: it would
decide, without telling anyone, whether an absent motor gets polled.
"""

from __future__ import annotations

# Status codes come from the stdlib rather than `fastapi.status`: the framework renamed its 422
# constant and kept the old name as a deprecated alias, so either spelling is wrong on some
# supported version.
from http import HTTPStatus
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException
from pydantic import ValidationError

from backend.config.constants import (
    CONFIG_ROUTE,
    CONFIG_SUBOBJECT_ROUTE,
    FIELD_GRIPPER_MOTOR,
    FIELD_LABEL,
    FIELD_TOOL_ID,
    TOOLS_ROUTE,
)
from backend.config.store import RuntimeConfigStore, UnknownSubobjectError
from backend.endeffector import ToolDefinition, registered_tools

API_TITLE = "OpenArm runtime configuration"


def tool_choice(tool: ToolDefinition) -> dict[str, Any]:
    """Map one registered tool onto the choice shape the GUI renders."""
    return {
        FIELD_TOOL_ID: tool.tool_id,
        FIELD_LABEL: tool.label,
        FIELD_GRIPPER_MOTOR: tool.gripper_motor,
    }


def _validation_detail(error: ValidationError) -> list[str]:
    """Flatten a pydantic failure into JSON-safe reasons.

    `ValidationError.errors()` carries the original exception object in `ctx`, which does not
    serialize; the message is what names the admissible values, so only that is kept.
    """
    return [
        f"{'.'.join(str(part) for part in entry['loc']) or '<body>'}: {entry['msg']}"
        for entry in error.errors()
    ]


def create_app(store: RuntimeConfigStore) -> FastAPI:
    """Build the config API over one store.

    Args:
        store: Where the document lives. Supplied by the caller so a host, a test and a
            deployment can each point at their own directory.

    Returns:
        (FastAPI) An application with the three config routes mounted, bound to nothing.
    """
    app = FastAPI(title=API_TITLE)

    @app.get(TOOLS_ROUTE)
    def read_tools() -> list[dict[str, Any]]:
        """The registered tool choices.

        Declared ahead of the `{subobject}` route so this path is matched here rather than read
        as the name of a subobject.
        """
        return [tool_choice(tool) for tool in registered_tools()]

    @app.get(CONFIG_ROUTE)
    def read_config() -> dict[str, Any]:
        """The whole document, malformed subobjects replaced by their defaults."""
        return store.load().document.to_wire()

    @app.put(CONFIG_SUBOBJECT_ROUTE)
    def replace_subobject(
        subobject: str, payload: Annotated[dict[str, Any], Body()]
    ) -> dict[str, Any]:
        """Replace one subobject and return the whole document.

        Raises:
            HTTPException: 404 when `subobject` is not a key of the document, 422 when the
                payload does not satisfy that subobject's schema. Both name what would have been
                accepted, because the caller cannot fix a refusal it cannot read.
        """
        try:
            written = store.replace_subobject(subobject, payload)
        except UnknownSubobjectError as unknown:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(unknown)) from unknown
        except ValidationError as refused:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=_validation_detail(refused),
            ) from refused
        return written.document.to_wire()

    return app


__all__ = ["API_TITLE", "create_app", "tool_choice"]
