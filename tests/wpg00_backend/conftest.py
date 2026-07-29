"""Shared fixtures for the WP-G-00 backend acceptance tests.

Every test gets its own directory, so nothing here reads or writes the developer's real XDG
config. The client drives the routes in-process: `TestClient` speaks ASGI directly and binds no
port, which is what keeps the REST surface unit-testable.

`NON_DEFAULT_LAYOUT` is deliberately different from `LayoutConfig()` in both fields. A
preservation test against a subobject that already equals its default proves nothing — it passes
just as well when the subobject was wiped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.config import RuntimeConfigStore, create_app
from backend.config.constants import (
    FIELD_DENSITY,
    FIELD_SIDEBAR_COLLAPSED,
    FIELD_TOOL_ID,
    FIELD_TOOL_MASS_KG,
)
from backend.endeffector import SIDE_LEFT, SIDE_RIGHT, TOOL_GRIPPER

NON_DEFAULT_LAYOUT: dict[str, Any] = {
    FIELD_SIDEBAR_COLLAPSED: True,
    FIELD_DENSITY: "compact",
}

GRIPPER_ON_BOTH_ARMS: dict[str, Any] = {
    SIDE_LEFT: {FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: None},
    SIDE_RIGHT: {FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: None},
}


@pytest.fixture
def store(tmp_path: Path) -> RuntimeConfigStore:
    """A store over an empty per-test directory."""
    return RuntimeConfigStore(directory=tmp_path)


@pytest.fixture
def client(store: RuntimeConfigStore) -> TestClient:
    """A client over the config routes, bound to no socket."""
    return TestClient(create_app(store))


def write_raw_document(store: RuntimeConfigStore, raw: object) -> None:
    """Put an arbitrary JSON value on disk, bypassing every model.

    This is how a hand-edited or half-migrated file is modelled: the store's own writer cannot
    produce a malformed document, so the read path's isolation has to be fed from outside it.
    """
    store.directory.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(raw), encoding="utf-8")
