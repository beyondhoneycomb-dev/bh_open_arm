"""The browser's copy of the camera routes and field names against the backend's originals.

The two are written in different languages and nothing binds them across that boundary, so the
only thing that keeps them equal is a test that reads both. A mismatch is not a build error: the
bundle compiles, the server starts, and the panel's fetch 404s — which reaches the operator as a
camera screen that shows no cameras, indistinguishable from a rig with none plugged in.

Read out of the TypeScript source rather than imported, because that file is what the bundle is
built from.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.config.constants import (
    CAMERA_DEVICES_ROUTE,
    CAMERA_PREVIEW_ROUTE,
    CAMERA_SLOT_ROUTE,
    FIELD_ASSIGNED_SLOT,
    FIELD_CARD,
    FIELD_DEVICE_PATH,
    FIELD_DEVICES,
    FIELD_PORT_PATH,
    FIELD_SLOTS,
    FIELD_UNBOUND_PORTS,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
ENDPOINTS_TS = _REPO_ROOT / "frontend" / "src" / "config" / "endpoints.ts"
SOURCE_TS = _REPO_ROOT / "frontend" / "src" / "screens" / "S-06" / "source.ts"
CLIENT_TS = _REPO_ROOT / "frontend" / "src" / "screens" / "S-06" / "deviceClient.ts"


def _const(text: str, name: str) -> str:
    """Read a `export const NAME = "value";` out of TypeScript source."""
    match = re.search(rf'export const {name} = "([^"]+)";', text)
    assert match is not None, f"{name} is not declared in the shell"
    return match.group(1)


def test_the_devices_route_is_one_string_in_two_languages() -> None:
    """A path the browser gets wrong is a 404 that reads as a rig with no cameras."""
    assert _const(ENDPOINTS_TS.read_text(encoding="utf-8"), "CAMERA_DEVICES_ENDPOINT") == (
        CAMERA_DEVICES_ROUTE
    )


def test_the_slot_route_shape_matches() -> None:
    """The browser builds this one, so the fixed part is what can be compared."""
    text = ENDPOINTS_TS.read_text(encoding="utf-8")
    prefix = CAMERA_SLOT_ROUTE.split("{", maxsplit=1)[0]

    assert f"`{prefix}${{encodeURIComponent(slot)}}`" in text


def test_the_preview_route_shape_matches() -> None:
    """Same, for the frame the operator decides against."""
    text = ENDPOINTS_TS.read_text(encoding="utf-8")
    suffix = CAMERA_PREVIEW_ROUTE.rsplit("}", maxsplit=1)[1]

    assert f"${{encodeURIComponent(portPath)}}{suffix}" in text


def test_every_device_row_field_is_read_by_the_browser() -> None:
    """A renamed field arrives as `undefined` — a row with no port, which is unassignable.

    Checked against the two files that consume it: the type the panel renders from and the
    client that parses the response.
    """
    consumed = SOURCE_TS.read_text(encoding="utf-8") + CLIENT_TS.read_text(encoding="utf-8")

    for field in (FIELD_PORT_PATH, FIELD_CARD, FIELD_DEVICE_PATH, FIELD_ASSIGNED_SLOT):
        assert field in consumed, field


def test_every_scan_envelope_field_is_read_by_the_browser() -> None:
    """The envelope the client destructures — a renamed key is an empty panel, silently."""
    client = CLIENT_TS.read_text(encoding="utf-8")

    for field in (FIELD_DEVICES, FIELD_SLOTS, FIELD_UNBOUND_PORTS):
        assert field in client, field


def test_the_assignment_body_key_is_the_one_the_backend_reads() -> None:
    """The backend reads `portPath` off the body; a different key is an empty port and a 422."""
    assert f"JSON.stringify({{ {FIELD_PORT_PATH} }})" in CLIENT_TS.read_text(encoding="utf-8")
