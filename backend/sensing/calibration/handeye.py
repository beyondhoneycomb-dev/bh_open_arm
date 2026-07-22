"""Five-method simultaneous hand-eye solve (WP-3B-13, `06` FR-CAM-025/026).

`06` FR-CAM-026 forbids a single-method result. The reason is on record in the
spec: `cv2.calibrateHandEye`'s TSAI branch returns wrong values for eye-to-hand
(opencv#20974), and "most hand-eye calibration methods don't work" in some pose
regimes (opencv#24871). The defence is to compute all five methods
simultaneously and present their mutual deviation, so an outlier is visible
rather than silently adopted. `HandEyeResult` therefore holds every method's
solution and exposes no accessor that collapses them to one "answer" — a caller
must read the deviation to decide whether the set even agrees.

Both mounting geometries of FR-CAM-025 are supported. An eye-in-hand camera (on
the wrist) recovers the camera-to-gripper transform; an eye-to-hand camera (fixed,
looking at the arm) recovers the camera-to-base transform, obtained by feeding the
inverted robot poses to the same solver.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations

import cv2
import numpy as np
from numpy.typing import NDArray

from backend.sensing.calibration.constants import HAND_EYE_METHOD_NAMES, MIN_POSES_FOR_HAND_EYE
from backend.sensing.calibration.errors import CalibrationInputError
from backend.sensing.calibration.transforms import (
    TransformRows,
    from_rows,
    invert,
    make_transform,
    relative_rotation_deg,
    rotation_of,
    to_rows,
    translation_distance_mm,
    translation_of,
)


class HandEyeSetup(Enum):
    """Which rigid relationship a camera's hand-eye calibration recovers.

    `06` FR-CAM-025: a wrist camera is eye-in-hand (moves with the gripper) and a
    fixed front/overhead camera is eye-to-hand (watches the arm move).
    """

    EYE_IN_HAND = "eye_in_hand"
    EYE_TO_HAND = "eye_to_hand"


# The `cv2.CALIB_HAND_EYE_*` flag for each named method. Kept here so the flag —
# a library-version-specific integer — never reaches a stored record, which keys
# on the method name alone (`constants.HAND_EYE_METHOD_NAMES`).
_METHOD_FLAGS = {
    "TSAI": cv2.CALIB_HAND_EYE_TSAI,
    "PARK": cv2.CALIB_HAND_EYE_PARK,
    "HORAUD": cv2.CALIB_HAND_EYE_HORAUD,
    "ANDREFF": cv2.CALIB_HAND_EYE_ANDREFF,
    "DANIILIDIS": cv2.CALIB_HAND_EYE_DANIILIDIS,
}


@dataclass(frozen=True)
class MethodSolution:
    """One method's recovered transform and its self-consistency residual.

    The residual is the AX=XB motion-pair error of *this* method's transform
    against the pose stream, split into a rotation and a translation part — the
    "잔차" FR-CAM-027 persists per method. A method that "doesn't work" for a pose
    set (opencv#24871) shows a large residual here even before it is compared to
    the others.

    Attributes:
        method: The method name, one of `HAND_EYE_METHOD_NAMES`.
        transform_rows: The recovered 4x4 transform, row-major.
        residual_rotation_deg: RMS rotation residual over motion pairs, degrees.
        residual_translation_mm: RMS translation residual over motion pairs, mm.
    """

    method: str
    transform_rows: TransformRows
    residual_rotation_deg: float
    residual_translation_mm: float

    def transform(self) -> NDArray[np.float64]:
        """Return the recovered transform as a 4x4 matrix."""
        return from_rows(self.transform_rows)


@dataclass(frozen=True)
class MethodDeviation:
    """The disagreement between two methods' recovered transforms.

    Attributes:
        method_a: First method name.
        method_b: Second method name.
        rotation_deg: Geodesic rotation angle between the two solutions, degrees.
        translation_mm: Translation distance between the two solutions, mm.
    """

    method_a: str
    method_b: str
    rotation_deg: float
    translation_mm: float


@dataclass(frozen=True)
class HandEyeResult:
    """The simultaneous five-method result and their pairwise deviations.

    There is deliberately no accessor that returns "the" transform. `06`
    FR-CAM-026 forbids a single-method adoption UI, and the type enforces it: the
    only way to read the outcome is through `solutions` (all five) and
    `deviations`, so a consumer cannot render one method without having the
    disagreement in hand. `exceeds_agreement` turns that disagreement into the
    `06` `RETRY_WITH_VARIANT` decision (re-collect poses), but the thresholds are
    the caller's — the subsystem invents no spec value (FR-CAM-030 is unmeasured).

    Attributes:
        setup: The mounting geometry the transforms are expressed in.
        sample_pose_count: Number of input poses the solve consumed.
        solutions: One `MethodSolution` per method, in `HAND_EYE_METHOD_NAMES`
            order.
        deviations: Pairwise deviations across all method pairs.
    """

    setup: HandEyeSetup
    sample_pose_count: int
    solutions: tuple[MethodSolution, ...]
    deviations: tuple[MethodDeviation, ...]

    def methods(self) -> tuple[str, ...]:
        """Return the method names present, in canonical order."""
        return tuple(solution.method for solution in self.solutions)

    def max_rotation_deviation_deg(self) -> float:
        """Return the largest pairwise rotation deviation, degrees (0.0 if <2 methods)."""
        return max((deviation.rotation_deg for deviation in self.deviations), default=0.0)

    def max_translation_deviation_mm(self) -> float:
        """Return the largest pairwise translation deviation, mm (0.0 if <2 methods)."""
        return max((deviation.translation_mm for deviation in self.deviations), default=0.0)

    def exceeds_agreement(self, max_rotation_deg: float, max_translation_mm: float) -> bool:
        """Whether the methods disagree beyond caller-supplied tolerances.

        A True result is `06`'s `RETRY_WITH_VARIANT` trigger: the sample poses are
        re-collected because the five methods do not corroborate one solution.

        Args:
            max_rotation_deg: The rotation-agreement tolerance, degrees.
            max_translation_mm: The translation-agreement tolerance, mm.

        Returns:
            (bool) True when either the rotation or translation deviation exceeds
            its tolerance.
        """
        return (
            self.max_rotation_deviation_deg() > max_rotation_deg
            or self.max_translation_deviation_mm() > max_translation_mm
        )


def _as_transforms(poses: object, label: str) -> list[NDArray[np.float64]]:
    """Coerce a sequence of 4x4 pose payloads into validated transform matrices."""
    matrices = [from_rows(pose) for pose in poses]  # type: ignore[union-attr]
    if len(matrices) < MIN_POSES_FOR_HAND_EYE:
        raise CalibrationInputError(
            f"{label}: hand-eye needs at least {MIN_POSES_FOR_HAND_EYE} poses, got {len(matrices)}"
        )
    return matrices


def _cv_inputs(
    robot_poses: list[NDArray[np.float64]],
    target_poses: list[NDArray[np.float64]],
    setup: HandEyeSetup,
) -> tuple[list[NDArray[np.float64]], list[NDArray[np.float64]]]:
    """Return the (hand, eye) transform streams passed to `cv2.calibrateHandEye`.

    For eye-in-hand the hand stream is gripper-to-base directly. For eye-to-hand
    the camera is fixed and the arm carries the target, so the base poses are
    inverted (base-to-gripper) and the solver then recovers camera-to-base. Either
    way the recovered X satisfies `A X = X B` where A is the hand-stream motion and
    B the eye-stream motion, which is what the residual reads.

    Args:
        robot_poses: Gripper-to-base transforms, one per sample.
        target_poses: Target-to-camera transforms, one per sample.
        setup: The mounting geometry.

    Returns:
        (tuple) The hand-transform stream and the eye-transform stream.
    """
    eye = target_poses
    if setup is HandEyeSetup.EYE_IN_HAND:
        return robot_poses, eye
    return [invert(pose) for pose in robot_poses], eye


def _residual(
    transform: NDArray[np.float64],
    hand: list[NDArray[np.float64]],
    eye: list[NDArray[np.float64]],
) -> tuple[float, float]:
    """Return the AX=XB RMS residual of a solution, as (rotation deg, translation mm).

    For each consecutive pose pair the hand motion A and eye motion B must satisfy
    `A X = X B`. The residual is how far the recovered X misses that, RMS-averaged
    over the pairs — 0 for a solution consistent with the motions, large for a
    method that failed on this pose set.

    Args:
        transform: A recovered 4x4 hand-eye transform.
        hand: The hand-transform stream (`_cv_inputs`).
        eye: The eye-transform stream (`_cv_inputs`).

    Returns:
        (tuple) RMS rotation residual (degrees) and translation residual (mm).
    """
    rotation_terms: list[float] = []
    translation_terms: list[float] = []
    for i in range(len(hand) - 1):
        motion_hand = invert(hand[i + 1]) @ hand[i]
        motion_eye = eye[i + 1] @ invert(eye[i])
        left = motion_hand @ transform
        right = transform @ motion_eye
        rotation_terms.append(relative_rotation_deg(rotation_of(left), rotation_of(right)))
        translation_terms.append(
            translation_distance_mm(translation_of(left), translation_of(right))
        )
    rotation_rms = float(np.sqrt(np.mean(np.square(rotation_terms)))) if rotation_terms else 0.0
    translation_rms = (
        float(np.sqrt(np.mean(np.square(translation_terms)))) if translation_terms else 0.0
    )
    return rotation_rms, translation_rms


def _deviations(solutions: tuple[MethodSolution, ...]) -> tuple[MethodDeviation, ...]:
    """Compute pairwise rotation/translation deviations across every method pair."""
    deviations: list[MethodDeviation] = []
    for left, right in combinations(solutions, 2):
        a = left.transform()
        b = right.transform()
        deviations.append(
            MethodDeviation(
                method_a=left.method,
                method_b=right.method,
                rotation_deg=relative_rotation_deg(rotation_of(a), rotation_of(b)),
                translation_mm=translation_distance_mm(translation_of(a), translation_of(b)),
            )
        )
    return tuple(deviations)


def solve_hand_eye_all_methods(
    robot_poses: object,
    target_poses: object,
    setup: HandEyeSetup,
) -> HandEyeResult:
    """Solve hand-eye with all five methods at once and report their deviations.

    The identical routine serves the offline synthetic acceptance and the deferred
    real-capture reverify hook; only the source of the poses differs. Every method
    in `HAND_EYE_METHOD_NAMES` is computed, so the result can never present one
    method without the others (FR-CAM-026).

    Args:
        robot_poses: Gripper-to-base transforms (4x4 each), one per sample.
        target_poses: Target-to-camera transforms (4x4 each), one per sample.
        setup: Eye-in-hand or eye-to-hand mounting geometry.

    Returns:
        (HandEyeResult) All five solutions and their pairwise deviations.

    Raises:
        CalibrationInputError: If the two pose streams differ in length or are
            shorter than the solver minimum.
    """
    robots = _as_transforms(robot_poses, "robot_poses")
    targets = _as_transforms(target_poses, "target_poses")
    if len(robots) != len(targets):
        raise CalibrationInputError(
            f"robot_poses ({len(robots)}) and target_poses ({len(targets)}) must be equal length"
        )

    hand, eye = _cv_inputs(robots, targets, setup)
    hand_rotations = [rotation_of(pose) for pose in hand]
    hand_translations = [translation_of(pose) for pose in hand]
    eye_rotations = [rotation_of(pose) for pose in eye]
    eye_translations = [translation_of(pose) for pose in eye]

    solutions: list[MethodSolution] = []
    for method in HAND_EYE_METHOD_NAMES:
        rotation, translation = cv2.calibrateHandEye(
            hand_rotations,
            hand_translations,
            eye_rotations,
            eye_translations,
            method=_METHOD_FLAGS[method],
        )
        transform = make_transform(
            np.asarray(rotation, dtype=np.float64), np.asarray(translation, dtype=np.float64)
        )
        residual_rotation, residual_translation = _residual(transform, hand, eye)
        solutions.append(
            MethodSolution(
                method=method,
                transform_rows=tuple(tuple(row) for row in to_rows(transform)),  # type: ignore[arg-type]
                residual_rotation_deg=residual_rotation,
                residual_translation_mm=residual_translation,
            )
        )

    ordered = tuple(solutions)
    return HandEyeResult(
        setup=setup,
        sample_pose_count=len(robots),
        solutions=ordered,
        deviations=_deviations(ordered),
    )
