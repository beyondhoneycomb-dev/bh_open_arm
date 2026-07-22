"""Acceptance ① — five hand-eye methods computed simultaneously, deviation shown.

`02b` WP-3B-13 ①: the five methods (TSAI/PARK/HORAUD/ANDREFF/DANIILIDIS) compute
at once on a synthetic pose set and their per-method deviation (rotation deg,
translation mm) is presented side by side. `06` FR-CAM-026 makes a single-method
adoption a defect, so the result type is verified to expose no "the answer"
accessor. The negative branch — methods disagreeing beyond tolerance triggering
`RETRY_WITH_VARIANT` — is exercised by perturbing the poses.
"""

from __future__ import annotations

import cv2
import numpy as np

from backend.sensing.calibration import HandEyeResult, HandEyeSetup, solve_hand_eye_all_methods
from backend.sensing.calibration.constants import HAND_EYE_METHOD_NAMES
from backend.sensing.calibration.synthetic import (
    synthetic_ground_truth_transform,
    synthetic_hand_eye_poses,
)
from backend.sensing.calibration.transforms import (
    relative_rotation_deg,
    rotation_of,
    translation_distance_mm,
    translation_of,
)

_CLEAN_ROTATION_TOL_DEG = 1e-3
_CLEAN_TRANSLATION_TOL_MM = 1e-3


def _perturb(poses: list[list[list[float]]], seed: int, sigma: float) -> list[list[list[float]]]:
    """Add seeded Gaussian noise to each pose's rotation and translation.

    A perturbed target-pose stream makes the five methods diverge, standing in for
    the noisy `solvePnP` a real capture would feed the solver.
    """
    rng = np.random.default_rng(seed)
    noisy: list[list[list[float]]] = []
    for pose in poses:
        matrix = np.asarray(pose, dtype=np.float64)
        rvec, _ = cv2.Rodrigues(matrix[:3, :3])
        rvec = rvec + rng.normal(0.0, sigma, size=rvec.shape)
        rotation, _ = cv2.Rodrigues(rvec)
        matrix[:3, :3] = rotation
        matrix[:3, 3] = matrix[:3, 3] + rng.normal(0.0, sigma * 0.5, size=3)
        noisy.append([[float(v) for v in row] for row in matrix])
    return noisy


def test_all_five_methods_computed_in_canonical_order() -> None:
    """Every mandated method is solved, in the canonical presentation order."""
    ground_truth = synthetic_ground_truth_transform(7)
    robot_poses, target_poses = synthetic_hand_eye_poses(
        ground_truth, 14, HandEyeSetup.EYE_IN_HAND, 7
    )

    result = solve_hand_eye_all_methods(robot_poses, target_poses, HandEyeSetup.EYE_IN_HAND)

    assert result.methods() == HAND_EYE_METHOD_NAMES
    assert len(result.solutions) == len(HAND_EYE_METHOD_NAMES)


def test_methods_recover_ground_truth_on_clean_poses() -> None:
    """On a consistent pose set every method recovers the ground-truth transform."""
    ground_truth = synthetic_ground_truth_transform(3)
    robot_poses, target_poses = synthetic_hand_eye_poses(
        ground_truth, 16, HandEyeSetup.EYE_IN_HAND, 3
    )

    result = solve_hand_eye_all_methods(robot_poses, target_poses, HandEyeSetup.EYE_IN_HAND)

    for solution in result.solutions:
        transform = solution.transform()
        rotation_error = relative_rotation_deg(rotation_of(transform), rotation_of(ground_truth))
        translation_error = translation_distance_mm(
            translation_of(transform), translation_of(ground_truth)
        )
        assert rotation_error < _CLEAN_ROTATION_TOL_DEG, solution.method
        assert translation_error < _CLEAN_TRANSLATION_TOL_MM, solution.method


def test_eye_to_hand_recovers_ground_truth() -> None:
    """The eye-to-hand geometry (FR-CAM-025) recovers its camera-to-base transform."""
    ground_truth = synthetic_ground_truth_transform(21)
    robot_poses, target_poses = synthetic_hand_eye_poses(
        ground_truth, 15, HandEyeSetup.EYE_TO_HAND, 21
    )

    result = solve_hand_eye_all_methods(robot_poses, target_poses, HandEyeSetup.EYE_TO_HAND)

    assert result.setup is HandEyeSetup.EYE_TO_HAND
    for solution in result.solutions:
        rotation_error = relative_rotation_deg(
            rotation_of(solution.transform()), rotation_of(ground_truth)
        )
        assert rotation_error < _CLEAN_ROTATION_TOL_DEG, solution.method


def test_deviation_and_residual_presented_per_method() -> None:
    """Each method carries a residual, and pairwise deviations cover every pair."""
    ground_truth = synthetic_ground_truth_transform(9)
    robot_poses, target_poses = synthetic_hand_eye_poses(
        ground_truth, 12, HandEyeSetup.EYE_IN_HAND, 9
    )

    result = solve_hand_eye_all_methods(robot_poses, target_poses, HandEyeSetup.EYE_IN_HAND)

    method_count = len(HAND_EYE_METHOD_NAMES)
    assert len(result.deviations) == method_count * (method_count - 1) // 2
    for solution in result.solutions:
        assert solution.residual_rotation_deg >= 0.0
        assert solution.residual_translation_mm >= 0.0
    for deviation in result.deviations:
        assert deviation.method_a != deviation.method_b
        assert deviation.rotation_deg >= 0.0
        assert deviation.translation_mm >= 0.0


def test_no_single_method_answer_accessor() -> None:
    """The result exposes no accessor that collapses the five to one (FR-CAM-026).

    A single-method adoption UI is forbidden; the type is the enforcement. The
    outcome is readable only as the full `solutions` set plus `deviations`, so a
    consumer cannot render one method without the disagreement in hand.
    """
    forbidden = {"best", "chosen", "answer", "transform", "solution", "winner", "adopt"}
    attributes = {name for name in dir(HandEyeResult) if not name.startswith("_")}
    assert forbidden.isdisjoint(attributes), forbidden & attributes


def test_clean_poses_agree_within_tolerance() -> None:
    """A consistent pose set does not trip the disagreement threshold."""
    ground_truth = synthetic_ground_truth_transform(4)
    robot_poses, target_poses = synthetic_hand_eye_poses(
        ground_truth, 16, HandEyeSetup.EYE_IN_HAND, 4
    )

    result = solve_hand_eye_all_methods(robot_poses, target_poses, HandEyeSetup.EYE_IN_HAND)

    assert not result.exceeds_agreement(max_rotation_deg=0.01, max_translation_mm=0.01)


def test_disagreeing_poses_trigger_retry_variant() -> None:
    """Noisy poses make the methods diverge past tolerance — the RETRY_WITH_VARIANT trigger.

    `02b` WP-3B-13 negative branch: excessive inter-method deviation calls for
    re-collecting the sample poses. `exceeds_agreement` is that decision, and it
    fires here where a clean set (above) did not.
    """
    ground_truth = synthetic_ground_truth_transform(4)
    robot_poses, target_poses = synthetic_hand_eye_poses(
        ground_truth, 16, HandEyeSetup.EYE_IN_HAND, 4
    )
    noisy_targets = _perturb(target_poses, seed=99, sigma=0.03)

    result = solve_hand_eye_all_methods(robot_poses, noisy_targets, HandEyeSetup.EYE_IN_HAND)

    assert result.max_rotation_deviation_deg() > 0.01
    assert result.exceeds_agreement(max_rotation_deg=0.01, max_translation_mm=0.01)
