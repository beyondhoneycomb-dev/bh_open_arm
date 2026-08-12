"""The three REST routes, driven in-process.

Nothing here binds a socket: `TestClient` speaks ASGI to the application object `create_app`
returns. The refusal assertions check the response *body*, not only the status — a 4xx that does
not name what would have been accepted leaves the caller with nothing to correct.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi.testclient import TestClient

from backend.config.constants import (
    CONFIG_ROUTE,
    FIELD_GRIPPER_MOTOR,
    FIELD_LABEL,
    FIELD_TOOL_ID,
    FIELD_TOOL_MASS_KG,
    SUBOBJECT_CONTROL,
    SUBOBJECT_END_EFFECTOR,
    SUBOBJECT_LAYOUT,
    SUBOBJECT_PRESETS,
    SUBOBJECT_THEME,
    TOOLS_ROUTE,
)
from backend.config.store import RuntimeConfigStore
from backend.endeffector import DEFAULT_TOOL_ID, SIDE_LEFT, SIDE_RIGHT, TOOL_GRIPPER
from backend.endeffector import registered_tools as registry_tools
from tests.wpg00_backend.conftest import (
    GRIPPER_ON_BOTH_ARMS,
    NON_DEFAULT_LAYOUT,
    write_raw_document,
)

UNREGISTERED_TOOL_ID = "vacuum_cup"
MEASURED_MASS_KG = 0.42


def subobject_route(key: str) -> str:
    """The PUT path for one subobject."""
    return f"{CONFIG_ROUTE}/{key}"


def test_get_returns_the_whole_document(client: TestClient) -> None:
    """Every subobject, camelCase, nothing else — what the browser client parses."""
    body = client.get(CONFIG_ROUTE).json()

    assert set(body) == {
        SUBOBJECT_LAYOUT,
        SUBOBJECT_THEME,
        SUBOBJECT_PRESETS,
        SUBOBJECT_END_EFFECTOR,
        SUBOBJECT_CONTROL,
    }


def test_default_document_has_both_arms_on_the_no_gripper_tool(client: TestClient) -> None:
    """Before anything is chosen, neither arm claims a motor on `0x08`."""
    end_effector = client.get(CONFIG_ROUTE).json()[SUBOBJECT_END_EFFECTOR]

    assert end_effector[SIDE_LEFT][FIELD_TOOL_ID] == DEFAULT_TOOL_ID
    assert end_effector[SIDE_RIGHT][FIELD_TOOL_ID] == DEFAULT_TOOL_ID


def test_tool_choices_come_from_the_registry(client: TestClient) -> None:
    """The GUI's choices are `registered_tools()` mapped onto the wire, never a second list.

    Compared against the registry rather than against a literal: a test carrying its own copy of
    the tool list would keep passing after a tool is added and the route stops reporting it.
    """
    choices = client.get(TOOLS_ROUTE).json()

    assert choices == [
        {
            FIELD_TOOL_ID: tool.tool_id,
            FIELD_LABEL: tool.label,
            FIELD_GRIPPER_MOTOR: tool.gripper_motor,
        }
        for tool in registry_tools()
    ]


def test_tools_route_is_not_read_as_a_subobject_name(client: TestClient) -> None:
    """`/api/config/tools` resolves to the choices, not to a subobject called `tools`."""
    response = client.get(TOOLS_ROUTE)

    assert response.status_code == HTTPStatus.OK
    assert isinstance(response.json(), list)


def test_put_one_subobject_leaves_the_others(client: TestClient) -> None:
    """Blast-radius isolation on the write path: a layout change must not re-answer `0x08`."""
    client.put(subobject_route(SUBOBJECT_END_EFFECTOR), json=GRIPPER_ON_BOTH_ARMS)

    body = client.put(subobject_route(SUBOBJECT_LAYOUT), json=NON_DEFAULT_LAYOUT).json()

    assert body[SUBOBJECT_END_EFFECTOR][SIDE_LEFT][FIELD_TOOL_ID] == TOOL_GRIPPER
    assert body[SUBOBJECT_LAYOUT] == NON_DEFAULT_LAYOUT


def test_malformed_end_effector_on_disk_leaves_layout_intact(
    client: TestClient, store: RuntimeConfigStore
) -> None:
    """CG-G-00d over REST: the operator's layout survives a corrupt `endEffector` record."""
    write_raw_document(
        store,
        {
            SUBOBJECT_LAYOUT: NON_DEFAULT_LAYOUT,
            SUBOBJECT_END_EFFECTOR: {SIDE_LEFT: {FIELD_TOOL_ID: UNREGISTERED_TOOL_ID}},
        },
    )

    body = client.get(CONFIG_ROUTE).json()

    assert body[SUBOBJECT_LAYOUT] == NON_DEFAULT_LAYOUT
    assert body[SUBOBJECT_END_EFFECTOR][SIDE_LEFT][FIELD_TOOL_ID] == DEFAULT_TOOL_ID


def test_unregistered_tool_id_is_refused_with_the_known_ids_listed(client: TestClient) -> None:
    """Not a silent default: the answer decides whether an absent motor gets polled."""
    response = client.put(
        subobject_route(SUBOBJECT_END_EFFECTOR),
        json={
            SIDE_LEFT: {FIELD_TOOL_ID: UNREGISTERED_TOOL_ID, FIELD_TOOL_MASS_KG: None},
            SIDE_RIGHT: {FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: None},
        },
    )

    assert HTTPStatus.BAD_REQUEST <= response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
    detail = str(response.json()["detail"])
    assert UNREGISTERED_TOOL_ID in detail
    for tool in registry_tools():
        assert tool.tool_id in detail


def test_a_refused_put_changes_nothing_on_disk(client: TestClient) -> None:
    """The refusal is total: no half of the payload reaches the document."""
    client.put(subobject_route(SUBOBJECT_END_EFFECTOR), json=GRIPPER_ON_BOTH_ARMS)

    client.put(
        subobject_route(SUBOBJECT_END_EFFECTOR),
        json={
            SIDE_LEFT: {FIELD_TOOL_ID: DEFAULT_TOOL_ID, FIELD_TOOL_MASS_KG: None},
            SIDE_RIGHT: {FIELD_TOOL_ID: UNREGISTERED_TOOL_ID, FIELD_TOOL_MASS_KG: None},
        },
    )

    end_effector = client.get(CONFIG_ROUTE).json()[SUBOBJECT_END_EFFECTOR]
    assert end_effector[SIDE_LEFT][FIELD_TOOL_ID] == TOOL_GRIPPER
    assert end_effector[SIDE_RIGHT][FIELD_TOOL_ID] == TOOL_GRIPPER


def test_null_tool_mass_round_trips_as_null(client: TestClient) -> None:
    """Unmeasured travels as null and blocks nothing."""
    client.put(subobject_route(SUBOBJECT_END_EFFECTOR), json=GRIPPER_ON_BOTH_ARMS)

    end_effector = client.get(CONFIG_ROUTE).json()[SUBOBJECT_END_EFFECTOR]

    assert end_effector[SIDE_LEFT][FIELD_TOOL_MASS_KG] is None
    assert end_effector[SIDE_RIGHT][FIELD_TOOL_MASS_KG] is None


def test_measured_tool_mass_round_trips_as_the_number_given(client: TestClient) -> None:
    """A weighed tool keeps its number to the byte."""
    client.put(
        subobject_route(SUBOBJECT_END_EFFECTOR),
        json={
            SIDE_LEFT: {FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: MEASURED_MASS_KG},
            SIDE_RIGHT: {FIELD_TOOL_ID: DEFAULT_TOOL_ID, FIELD_TOOL_MASS_KG: None},
        },
    )

    end_effector = client.get(CONFIG_ROUTE).json()[SUBOBJECT_END_EFFECTOR]

    assert end_effector[SIDE_LEFT][FIELD_TOOL_MASS_KG] == MEASURED_MASS_KG


def test_zero_tool_mass_is_refused(client: TestClient) -> None:
    """An unmeasured tool is null, not zero — zero is a number nobody weighed."""
    response = client.put(
        subobject_route(SUBOBJECT_END_EFFECTOR),
        json={
            SIDE_LEFT: {FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: 0},
            SIDE_RIGHT: {FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: None},
        },
    )

    assert HTTPStatus.BAD_REQUEST <= response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
    assert FIELD_TOOL_MASS_KG in str(response.json()["detail"])


def test_unknown_subobject_is_refused_with_the_known_keys_listed(client: TestClient) -> None:
    """A PUT to a key the document does not have is a 404, not a new key."""
    response = client.put(subobject_route("layouts"), json={})

    assert response.status_code == HTTPStatus.NOT_FOUND
    detail = str(response.json()["detail"])
    assert SUBOBJECT_LAYOUT in detail
    assert SUBOBJECT_END_EFFECTOR in detail


def test_extra_field_in_a_put_payload_is_refused(client: TestClient) -> None:
    """`extra="forbid"` reaches the wire: a field nothing reads is not quietly accepted."""
    response = client.put(
        subobject_route(SUBOBJECT_LAYOUT), json={**NON_DEFAULT_LAYOUT, "sidebarWidthPx": 240}
    )

    assert HTTPStatus.BAD_REQUEST <= response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
