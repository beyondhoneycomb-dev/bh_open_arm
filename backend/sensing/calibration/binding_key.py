"""The rigid-relationship identity a calibration is bound to (WP-3B-13).

`06` FR-CAM-028: a calibration describes the rigid body formed by a specific camera
mounted at a specific place. Three things change that body and invalidate the
extrinsic:

* the camera **serial** — a different physical camera has a different lens/sensor
  and a different mount seat,
* the **slot** — the same camera moved to another logical slot is a different
  camera-to-arm relationship,
* the **mount** — remounting the same camera in the same slot perturbs the rigid
  offset the hand-eye solve measured.

The binding key is the tuple of those three. A stored calibration records the key
it was captured under; when the live key differs on any field the calibration is
stale (`store.is_stale`), and stale blocks collection start.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CalibrationBindingKey:
    """The (serial, slot, mount) identity a calibration is valid for.

    Attributes:
        camera_serial: The stable camera serial (a RealSense serial or a webcam
            udev by-id), the same identifier `backend.camera.binding` pins slots by.
        slot_key: The `CTR-PRIM@v1` camera slot key string.
        mount_id: An operator-declared identifier for the physical mount seat; a
            remount is recorded by changing it, which is what makes a remount
            observable to the stale check.
    """

    camera_serial: str
    slot_key: str
    mount_id: str

    def changed_fields(self, other: CalibrationBindingKey) -> tuple[str, ...]:
        """Return the field names that differ from another key, for a stale reason.

        Args:
            other: The key to compare against (typically the live binding).

        Returns:
            (tuple[str, ...]) The differing field names, in a stable order.
        """
        differences: list[str] = []
        if self.camera_serial != other.camera_serial:
            differences.append("camera_serial")
        if self.slot_key != other.slot_key:
            differences.append("slot_key")
        if self.mount_id != other.mount_id:
            differences.append("mount_id")
        return tuple(differences)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to plain types for the YAML record."""
        return {
            "camera_serial": self.camera_serial,
            "slot_key": self.slot_key,
            "mount_id": self.mount_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibrationBindingKey:
        """Rebuild from a YAML record payload."""
        return cls(
            camera_serial=str(data["camera_serial"]),
            slot_key=str(data["slot_key"]),
            mount_id=str(data["mount_id"]),
        )
