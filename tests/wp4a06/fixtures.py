"""Shared fixtures for the WP-4A-06 projection tests (`02c` §1.6).

Every case is built from the COMMITTED synthetic 48-dim dataset
(`contracts.fixtures.synthetic_dataset.build_synthetic_dataset`) and the committed
WP-4A-02 `derive_observation_config`, consumed by reference — the observation names
are never re-spelt here, so a change to the recorder grammar reaches these tests.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.training.preflight import ObservationConfig, derive_observation_config
from backend.training.projection import ArmRequest, ProjectionKind
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset

# The five FR-TRN-073 shared controls, by attribute name and a matched baseline
# value. `CG-4A-06b` mutates one at a time to prove each is enforced.
SHARED_CONTROL_FIELDS = (
    "repo_id",
    "revision",
    "seed",
    "rollout_set_id",
    "success_criterion_id",
)

_BASELINE_CONTROLS = {
    "repo_id": "openarm/contact_rich",
    "revision": "0123abc",
    "seed": 7,
    "rollout_set_id": "contact_suite_v1",
    "success_criterion_id": "insertion_ok_v1",
}

# A source snippet that DOES leak a torque into an action target — the positive
# control proving the static scan bites rather than passing vacuously.
LEAK_SOURCE = (
    "from contracts.action import AcceptedPositionAction\n"
    "def build(gravity_torque):\n"
    "    return AcceptedPositionAction(values=gravity_torque)\n"
)

# A source snippet that constructs an action target from a position value only —
# the negative control the scan must leave clean.
CLEAN_SOURCE = (
    "from contracts.action import AcceptedPositionAction\n"
    "def build(position_values):\n"
    "    return AcceptedPositionAction(values=position_values)\n"
)


def observation_config() -> ObservationConfig:
    """Return the committed 48-dim observation configuration.

    Returns:
        (ObservationConfig) Derived from the synthetic bimanual vel/torque fixture.
    """
    dataset = build_synthetic_dataset()
    return derive_observation_config(dataset.info_features)


def observation_names() -> tuple[str, ...]:
    """Return the fixture's `observation.state` channel names.

    Returns:
        (tuple[str, ...]) The 48 interleaved per-motor channel names.
    """
    return observation_config().names


def rotated(names: Sequence[str], by: int) -> tuple[str, ...]:
    """Return the names rotated left by `by` positions.

    A rotation preserves the channel set but moves every position, so a positional
    selector picks a different physical set while a name-derived one does not.

    Args:
        names: The channel names to rotate.
        by: The number of positions to rotate left.

    Returns:
        (tuple[str, ...]) The rotated names.
    """
    offset = by % len(names)
    return tuple(names[offset:]) + tuple(names[:offset])


def arm_request(projection: ProjectionKind, **overrides: object) -> ArmRequest:
    """Build an arm request on the matched baseline, with optional control overrides.

    Args:
        projection: The projection this arm trains on.
        overrides: Shared-control values to override the baseline with.

    Returns:
        (ArmRequest) The arm request.
    """
    controls = dict(_BASELINE_CONTROLS)
    controls.update(overrides)  # type: ignore[arg-type]
    return ArmRequest(projection=projection, **controls)  # type: ignore[arg-type]


def matched_arm_pair() -> tuple[ArmRequest, ArmRequest]:
    """Return a FULL/POS_ONLY arm pair that agrees on all four controls.

    Returns:
        (tuple[ArmRequest, ArmRequest]) The FULL arm and the POS_ONLY arm.
    """
    return arm_request(ProjectionKind.FULL), arm_request(ProjectionKind.POS_ONLY)
