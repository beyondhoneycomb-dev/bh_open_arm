"""The persisted calibration record and its serialisation (WP-3B-13).

`06` FR-CAM-027 fixes what a calibration record must hold: the time it was
performed, the camera serial, the slot key, the sample-pose count, the per-method
results and their residuals. This module is that shape and its round-trip to plain
types; `persistence` writes it as YAML, `store` reads it back.

The record additionally carries a `provenance` flag distinguishing a calibration
solved from *synthetic* poses (the offline acceptance path) from one solved from a
*real capture* (the reverify hook). THE ONE RULE of this work package is that a
synthetic-derived intrinsic or extrinsic must never read as a measured one; the
flag is how a reader tells them apart, and the hardware path is the only thing that
stamps `REAL_CAPTURE`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from backend.sensing.calibration.binding_key import CalibrationBindingKey
from backend.sensing.calibration.handeye import (
    HandEyeResult,
    HandEyeSetup,
    MethodDeviation,
    MethodSolution,
)
from backend.sensing.calibration.intrinsics import CameraIntrinsics


class CalibrationProvenance(Enum):
    """Whether a record's numbers came from synthetic poses or a real capture.

    A record solved offline from `synthetic` data is `SYNTHETIC`; only the
    hardware reverify hook produces `REAL_CAPTURE`. The distinction is load-bearing:
    it is what stops a deterministic synthetic intrinsic from being mistaken for a
    measured one.
    """

    SYNTHETIC = "synthetic"
    REAL_CAPTURE = "real_capture"


@dataclass(frozen=True)
class CalibrationRecord:
    """One camera's persisted calibration (FR-CAM-027).

    Attributes:
        performed_at: ISO-8601 UTC timestamp of the calibration run.
        binding_key: The (serial, slot, mount) identity this calibration is valid
            for.
        sample_pose_count: The number of hand-eye sample poses used.
        provenance: Whether the numbers are synthetic or a real capture.
        hand_eye: The five-method hand-eye result, or None if only intrinsics were
            solved.
        intrinsics: The camera intrinsics, or None if only hand-eye was solved.
    """

    performed_at: str
    binding_key: CalibrationBindingKey
    sample_pose_count: int
    provenance: CalibrationProvenance
    hand_eye: HandEyeResult | None
    intrinsics: CameraIntrinsics | None

    @property
    def slot_key(self) -> str:
        """The camera slot key this record belongs to."""
        return self.binding_key.slot_key

    def to_yaml_dict(self) -> dict[str, Any]:
        """Serialise the whole record to plain types for YAML."""
        return {
            "performed_at": self.performed_at,
            "binding_key": self.binding_key.to_dict(),
            "sample_pose_count": int(self.sample_pose_count),
            "provenance": self.provenance.value,
            "hand_eye": _hand_eye_to_dict(self.hand_eye),
            "intrinsics": None if self.intrinsics is None else self.intrinsics.to_dict(),
        }

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> CalibrationRecord:
        """Rebuild a record from its YAML payload.

        Args:
            data: The mapping produced by `to_yaml_dict`.

        Returns:
            (CalibrationRecord) The reconstructed record.
        """
        intrinsics = data.get("intrinsics")
        return cls(
            performed_at=str(data["performed_at"]),
            binding_key=CalibrationBindingKey.from_dict(data["binding_key"]),
            sample_pose_count=int(data["sample_pose_count"]),
            provenance=CalibrationProvenance(data["provenance"]),
            hand_eye=_hand_eye_from_dict(data.get("hand_eye")),
            intrinsics=None if intrinsics is None else CameraIntrinsics.from_dict(intrinsics),
        )


def utc_now_iso() -> str:
    """Return the current instant as an ISO-8601 UTC timestamp (FR-CAM-027 일시)."""
    return datetime.now(UTC).isoformat()


def _hand_eye_to_dict(result: HandEyeResult | None) -> dict[str, Any] | None:
    """Serialise a hand-eye result — every method and every pairwise deviation."""
    if result is None:
        return None
    return {
        "setup": result.setup.value,
        "sample_pose_count": int(result.sample_pose_count),
        "solutions": [
            {
                "method": solution.method,
                "transform": [list(row) for row in solution.transform_rows],
                "residual_rotation_deg": float(solution.residual_rotation_deg),
                "residual_translation_mm": float(solution.residual_translation_mm),
            }
            for solution in result.solutions
        ],
        "deviations": [
            {
                "method_a": deviation.method_a,
                "method_b": deviation.method_b,
                "rotation_deg": float(deviation.rotation_deg),
                "translation_mm": float(deviation.translation_mm),
            }
            for deviation in result.deviations
        ],
    }


def _hand_eye_from_dict(data: dict[str, Any] | None) -> HandEyeResult | None:
    """Rebuild a hand-eye result from its payload."""
    if data is None:
        return None
    solutions = tuple(
        MethodSolution(
            method=str(entry["method"]),
            transform_rows=tuple(tuple(float(v) for v in row) for row in entry["transform"]),  # type: ignore[arg-type]
            residual_rotation_deg=float(entry["residual_rotation_deg"]),
            residual_translation_mm=float(entry["residual_translation_mm"]),
        )
        for entry in data["solutions"]
    )
    deviations = tuple(
        MethodDeviation(
            method_a=str(entry["method_a"]),
            method_b=str(entry["method_b"]),
            rotation_deg=float(entry["rotation_deg"]),
            translation_mm=float(entry["translation_mm"]),
        )
        for entry in data["deviations"]
    )
    return HandEyeResult(
        setup=HandEyeSetup(data["setup"]),
        sample_pose_count=int(data["sample_pose_count"]),
        solutions=solutions,
        deviations=deviations,
    )
