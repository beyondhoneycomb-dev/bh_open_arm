"""The surface S-06 assigns through: scan, assign, release, and what each refuses.

The panel is the only mechanism that can answer which wrist camera is which. Two Arducam B0495
report one serial, so no field a scan reads separates them — the operator looks at the picture and
decides, and this is where that decision is taken and persisted. Every refusal below is one that,
if it were instead silently corrected, would bind a slot to the wrong arm's camera and be
invisible in the footage.

Nothing here opens a camera: the enumeration is patched with fixture nodes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.camera import api as camera_api
from backend.camera.portpath import CaptureNode
from backend.camera.rig import BINDING_VERSION, binding_path

SLOTS = ("wrist_left", "wrist_right", "scene_stereo")

WRIST_CARD = "Arducam B0495 (USB3 2.3MP)"
LEFT_PORT = "usb-0000:00:0d.0-1.1.1"
RIGHT_PORT = "usb-0000:00:0d.0-1.1.3.4"
STEREO_PORT = "usb-0000:80:14.0-4.1"

PRESENT = (
    CaptureNode(device=Path("/dev/video2"), port_path=LEFT_PORT, card=WRIST_CARD),
    CaptureNode(device=Path("/dev/video4"), port_path=RIGHT_PORT, card=WRIST_CARD),
    CaptureNode(device=Path("/dev/video0"), port_path=STEREO_PORT, card="ZED-M: ZED-M"),
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """An app over a temp config directory, scanning a fixture camera set."""
    monkeypatch.setattr(camera_api, "enumerate_capture_nodes", lambda: PRESENT)
    app = FastAPI()
    camera_api.mount_camera_routes(app, tmp_path, SLOTS)
    return TestClient(app)


@pytest.fixture
def record(tmp_path: Path) -> Path:
    """Where the binding lands."""
    return binding_path(tmp_path)


def test_a_rig_with_no_record_lists_its_cameras_as_unassigned(client: TestClient) -> None:
    """The panel's whole job is to write the first record, so an absent one cannot refuse it.

    A 404 here would leave the operator with no way to create the thing whose absence they were
    just refused for.
    """
    body = client.get("/api/cameras/devices").json()

    assert [device["assignedSlot"] for device in body["devices"]] == [None, None, None]
    assert body["slots"] == list(SLOTS)


def test_the_rows_carry_the_port_the_card_and_the_node(client: TestClient) -> None:
    """All three, because on this rig the card is the same string on two of them.

    Without the port the two wrist rows are identical text; without the node an operator
    diagnosing a dead camera has nothing to `v4l2-ctl` at.
    """
    body = client.get("/api/cameras/devices").json()
    left = next(device for device in body["devices"] if device["portPath"] == LEFT_PORT)

    assert left["card"] == WRIST_CARD
    assert left["devicePath"] == "/dev/video2"


def test_rows_are_ordered_by_port_so_the_list_does_not_reshuffle(client: TestClient) -> None:
    """A list that reorders between scans moves the row under the operator's cursor."""
    ports = [device["portPath"] for device in client.get("/api/cameras/devices").json()["devices"]]

    assert ports == sorted(ports)


def test_an_assignment_reaches_disk_before_it_is_reported(client: TestClient, record: Path) -> None:
    """The response is re-scanned from the record, not echoed from the request.

    A panel told the assignment succeeded, over a write that did not land, shows a bound slot
    that is empty on the next start.
    """
    body = client.put("/api/cameras/slots/wrist_left", json={"portPath": LEFT_PORT}).json()

    assert json.loads(record.read_text())["slots"] == {"wrist_left": LEFT_PORT}
    left = next(device for device in body["devices"] if device["portPath"] == LEFT_PORT)
    assert left["assignedSlot"] == "wrist_left"


def test_assigning_a_camera_that_already_fills_another_slot_moves_it(
    client: TestClient, record: Path
) -> None:
    """One camera cannot be two slots — the runner opens each, and the second gets no frames.

    Moved rather than refused: the operator who just realised they had left and right backwards
    is doing exactly this, and refusing it would make the fix a two-step nobody guesses.
    """
    client.put("/api/cameras/slots/wrist_left", json={"portPath": LEFT_PORT})

    client.put("/api/cameras/slots/wrist_right", json={"portPath": LEFT_PORT})

    assert json.loads(record.read_text())["slots"] == {"wrist_right": LEFT_PORT}


def test_filling_a_slot_that_is_taken_replaces_its_camera(client: TestClient, record: Path) -> None:
    """A slot holds one camera. The panel warns before sending; the record cannot hold two."""
    client.put("/api/cameras/slots/wrist_left", json={"portPath": LEFT_PORT})

    client.put("/api/cameras/slots/wrist_left", json={"portPath": RIGHT_PORT})

    assert json.loads(record.read_text())["slots"] == {"wrist_left": RIGHT_PORT}


def test_a_slot_this_rig_does_not_have_is_refused(client: TestClient, record: Path) -> None:
    """404 rather than a written record: a slot nothing opens is a binding nothing reads."""
    response = client.put("/api/cameras/slots/wrist_third", json={"portPath": LEFT_PORT})

    assert response.status_code == 404
    assert "wrist_left" in response.json()["detail"]
    assert not record.exists()


def test_an_empty_port_is_refused(client: TestClient, record: Path) -> None:
    """An empty port pins the slot to nothing and reads back as bound (`06` FR-CAM-004)."""
    response = client.put("/api/cameras/slots/wrist_left", json={"portPath": "  "})

    assert response.status_code == 422
    assert not record.exists()


def test_releasing_a_slot_empties_it(client: TestClient, record: Path) -> None:
    """The operator took the camera off the arm; the record must stop claiming it is there."""
    client.put("/api/cameras/slots/wrist_left", json={"portPath": LEFT_PORT})

    body = client.delete("/api/cameras/slots/wrist_left").json()

    assert json.loads(record.read_text())["slots"] == {}
    assert all(device["assignedSlot"] is None for device in body["devices"])


def test_releasing_an_empty_slot_is_not_an_error(client: TestClient) -> None:
    """The intent is "this slot is empty", and it already is."""
    assert client.delete("/api/cameras/slots/wrist_left").status_code == 200


def test_a_camera_that_no_slot_claims_is_reported_and_is_not_a_failure(
    client: TestClient,
) -> None:
    """A fourth camera on this host is not this rig's problem, but the panel should say so."""
    client.put("/api/cameras/slots/wrist_left", json={"portPath": LEFT_PORT})

    body = client.get("/api/cameras/devices").json()

    assert sorted(body["unboundPorts"]) == sorted([RIGHT_PORT, STEREO_PORT])


def test_two_cameras_on_one_port_refuse_the_whole_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A port that names two nodes is an enumeration index wearing a port path.

    Refused rather than resolved to whichever enumerated first: that first is the ordering
    `06` FR-CAM-004 exists to keep a slot away from, and the operator would be assigning against
    a row that names a camera they cannot pick.
    """
    doubled = (
        CaptureNode(device=Path("/dev/video2"), port_path=LEFT_PORT, card=WRIST_CARD),
        CaptureNode(device=Path("/dev/video4"), port_path=LEFT_PORT, card=WRIST_CARD),
    )
    monkeypatch.setattr(camera_api, "enumerate_capture_nodes", lambda: doubled)
    app = FastAPI()
    camera_api.mount_camera_routes(app, tmp_path, SLOTS)

    response = TestClient(app).get("/api/cameras/devices")

    assert response.status_code == 409
    assert LEFT_PORT in response.json()["detail"]


def test_an_unreadable_record_is_refused_rather_than_read_as_an_empty_rig(
    client: TestClient, record: Path
) -> None:
    """An empty rig and a corrupt record look identical on screen, and only one is fixable."""
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"version": BINDING_VERSION + 1, "slots": {}}), encoding="utf-8")

    assert client.get("/api/cameras/devices").status_code == 422
