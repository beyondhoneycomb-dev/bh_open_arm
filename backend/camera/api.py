"""The REST surface S-06's device panel assigns against — scan, assign, release, preview.

`06` FR-CAM-004 binds a slot by a stable identifier and never by enumeration index. On this rig
the stable identifier has to be the USB port: both Arducam B0495 report the serial
`Arducam_202500915_0001`, so the driver hands back one `by-id` name for the pair and the second
camera has none. A port separates them; a port does not say *left*.

So the answer is the operator's, and this is the surface they give it through. The scan reports
what answered, the preview shows what each one is looking at, and the assignment is keyed on the
port and written to disk. Nothing here decides which camera is which — the panel shows the
picture and the person decides, which is the only mechanism that works on hardware whose devices
are identical by every field a scan can read.

**The preview is a still, one frame per request.** A slot's real stream belongs to the capture
run and the realtime channel; opening a second stream over the same node during a run would take
frames the run is counting. One frame on demand costs an open and a close, is enough to tell two
identical cameras apart, and cannot silently join a capture. The panel polls it while the
operator is deciding and stops when they navigate away.

Every refusal is a 4xx carrying the reason. A silently corrected assignment is the one outcome
this must never produce: it would decide which arm's view is which, without telling anyone, and
the mistake is invisible in the footage because both wrist cameras look alike.
"""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import Response

from backend.camera.portpath import (
    AmbiguousCameraPortError,
    CameraPortError,
    CaptureNode,
    discovery_rows,
    enumerate_capture_nodes,
)
from backend.camera.rig import (
    CameraBinding,
    CameraBindingError,
    assign_slot,
    binding_path,
    check_binding,
    load_binding,
    release_port,
    save_binding,
)
from backend.camera.snapshot import SnapshotUnavailableError, grab_jpeg
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

JPEG_MEDIA_TYPE = "image/jpeg"

# The preview is a live look at a device the operator is deciding about, so a cached one is
# worse than none: it would show the scene from before they pointed the camera.
NO_STORE = "no-store"


def _empty_binding() -> CameraBinding:
    """The binding a rig with no record has: nothing assigned, which is the truth on day one."""
    return CameraBinding(slots={})


def _read_binding(directory: Path) -> CameraBinding:
    """Load the record, or answer an empty one when none has been written yet.

    An absent file is not an error on this route. The panel's whole job is to write the first
    one, and refusing to list devices until a record exists would leave the operator no way to
    create it.
    """
    path = binding_path(directory)
    if not path.is_file():
        return _empty_binding()
    return load_binding(path)


def device_rows(nodes: tuple[CaptureNode, ...], binding: CameraBinding) -> list[dict[str, Any]]:
    """Render the scan as the rows S-06 assigns against, each carrying the slot it fills.

    Args:
        nodes: The capture nodes enumerated this scan.
        binding: The stored slot-to-port answer.

    Returns:
        (list) One row per camera, ordered by port so the panel's list does not reshuffle
        between scans.

    Raises:
        AmbiguousCameraPortError: If two cameras report one port.
    """
    slot_by_port = {port: slot for slot, port in binding.slots.items()}
    return [
        {
            FIELD_PORT_PATH: row["port_path"],
            FIELD_CARD: row["card"],
            FIELD_DEVICE_PATH: row["device_path"],
            FIELD_ASSIGNED_SLOT: slot_by_port.get(row["port_path"]),
        }
        for row in discovery_rows(nodes)
    ]


def mount_camera_routes(app: FastAPI, directory: Path, slots: tuple[str, ...]) -> None:
    """Mount the camera device routes onto an application.

    Args:
        app: The application to mount onto.
        directory: Where the binding record lives. Supplied by the caller so a host, a test and
            a deployment can each point at their own.
        slots: The slot names this rig has, in the order the panel offers them.
    """

    def scan() -> dict[str, Any]:
        """Enumerate what is plugged in now and pair it with the stored assignment."""
        try:
            nodes = enumerate_capture_nodes()
            binding = _read_binding(directory)
            rows = device_rows(nodes, binding)
            unbound = check_binding(binding, slots, nodes).unbound_ports
        except AmbiguousCameraPortError as ambiguous:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail=str(ambiguous)
            ) from ambiguous
        except CameraBindingError as unreadable:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(unreadable)
            ) from unreadable
        return {FIELD_DEVICES: rows, FIELD_SLOTS: list(slots), FIELD_UNBOUND_PORTS: list(unbound)}

    @app.get(CAMERA_DEVICES_ROUTE)
    def read_devices() -> dict[str, Any]:
        """What answered the bus this moment, and which slot each one fills.

        Scanned per call rather than cached: a camera plugged in after the page loaded exists
        only once somebody asks again, and a cached list would show a camera that is gone as
        assignable — which is how a slot ends up bound to nothing.
        """
        return scan()

    @app.put(CAMERA_SLOT_ROUTE)
    def assign_device(slot: str, payload: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        """Put the camera on the given port into `slot` and persist it.

        The write is atomic and the whole scan comes back, so the panel renders the state that
        actually reached disk rather than the one it asked for.

        Raises:
            HTTPException: 404 when the slot is not one this rig has, 422 when the port is
                empty or the stored record is unreadable, 409 when two cameras share a port.
        """
        port_path = str(payload.get(FIELD_PORT_PATH, "")).strip()
        try:
            amended = assign_slot(_read_binding(directory), slot, port_path, slots)
        except CameraBindingError as refused:
            status = HTTPStatus.NOT_FOUND if slot not in slots else HTTPStatus.UNPROCESSABLE_ENTITY
            raise HTTPException(status_code=status, detail=str(refused)) from refused
        save_binding(binding_path(directory), amended)
        return scan()

    @app.delete(CAMERA_SLOT_ROUTE)
    def release_slot(slot: str) -> dict[str, Any]:
        """Empty `slot` and persist it.

        Keyed on the slot rather than the port because the slot is what the record holds; the
        panel knows which slot a device fills and sends that.

        Raises:
            HTTPException: 422 when the stored record is unreadable.
        """
        try:
            binding = _read_binding(directory)
        except CameraBindingError as unreadable:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(unreadable)
            ) from unreadable
        port = binding.port_for(slot)
        if port is not None:
            save_binding(binding_path(directory), release_port(binding, port))
        return scan()

    @app.get(CAMERA_PREVIEW_ROUTE, response_class=Response)
    def read_preview(port_path: str) -> Response:
        """One JPEG frame from the camera on `port_path`.

        Raises:
            HTTPException: 404 when nothing is on that port, 409 when two cameras share it,
                503 when the device is there but would not hand over a frame — which on this
                bench is almost always a capture run already holding it.
        """
        try:
            frame = grab_jpeg(enumerate_capture_nodes(), port_path)
        except AmbiguousCameraPortError as ambiguous:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail=str(ambiguous)
            ) from ambiguous
        except CameraPortError as absent:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(absent)) from absent
        except SnapshotUnavailableError as busy:
            raise HTTPException(
                status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail=str(busy)
            ) from busy
        return Response(
            content=frame, media_type=JPEG_MEDIA_TYPE, headers={"Cache-Control": NO_STORE}
        )


__all__ = ["JPEG_MEDIA_TYPE", "device_rows", "mount_camera_routes"]
