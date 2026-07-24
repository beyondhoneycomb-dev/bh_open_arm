"""Derive an observation configuration from `meta/info.json` and verify its names.

`10` FR-TRN-061 fixes the one rule this module exists to hold: the observation
configuration is judged by the `names` array — specifically by whether a
`.torque` suffix is present — and NEVER by `observation.state`'s shape alone. A
recording whose shape is 48 but whose `names` carry no `.torque` is a *different*
configuration wearing a 48-wide coat, and a shape-only reader passes it. So
`state_dim` here is a value DERIVED from `names`, never the authority.

The names-integrity check compares the (post-rename) `names` against the canonical
per-motor order the recorder contract produces (`contracts.recorder.
observation_state_names`). It catches two faults with one comparison:

- the rename-map rotation (`FR-TRN-063`) — `build_dataset_frame` indexes
  `observation.state` by `names` order, so a rotation misaligns every channel
  with no exception raised; and
- the torque-stripped-but-shape-kept configuration (`FR-TRN-061`) — the `names`
  no longer form a valid `{.pos}`-only or `{.pos,.vel,.torque}` layout.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from backend.training.preflight.report import (
    Component,
    PreflightCode,
    PreflightFinding,
)
from contracts.prim import BIMANUAL_ACTION_DIM, SINGLE_ARM_ACTION_DIM
from contracts.recorder import (
    ACTION_KEY,
    OBSERVATION_STATE_KEY,
    TORQUE_SUFFIX,
    VELOCITY_SUFFIX,
    observation_state_names,
)

# The two arm prefixes a bimanual `names` array carries (`CTR-PRIM@v1`
# `ARM_PREFIXES`, left before right). Presence of either marks the two-arm layout;
# a single-arm recording carries bare motor keys.
_ARM_PREFIXES = ("left_", "right_")


@dataclass(frozen=True)
class ObservationConfig:
    """The observation configuration a dataset declares, judged by its `names`.

    `names` is canonical and `state_dim` is `len(names)` — a derived convenience,
    never the authority (`10` FR-TRN-061). `use_velocity_and_torque` is likewise
    read from the suffixes present in `names`, not inferred from the width.

    Attributes:
        use_velocity_and_torque: True iff a `.torque` channel is present in
            `names` — the canonical judgment, independent of shape.
        state_dim: `len(names)`; expected in {8, 16, 24, 48} for a valid layout,
            but stored as a plain width so an invalid derivation can be reported
            rather than raised.
        action_dim: `len(action names)`; expected in {8, 16}.
        names: The `observation.state` channel names as declared.
        bimanual: True when the layout carries arm-prefixed keys or a 16-wide
            action.
    """

    use_velocity_and_torque: bool
    state_dim: int
    action_dim: int
    names: tuple[str, ...]
    bimanual: bool


def _state_names(info_features: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the declared `observation.state` names, or an empty tuple when absent."""
    body = info_features.get(OBSERVATION_STATE_KEY)
    if not isinstance(body, Mapping):
        return ()
    return tuple(str(name) for name in body.get("names", []))


def _action_names(info_features: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the declared `action` names, or an empty tuple when absent."""
    body = info_features.get(ACTION_KEY)
    if not isinstance(body, Mapping):
        return ()
    return tuple(str(name) for name in body.get("names", []))


def _is_bimanual(state_names: Sequence[str], action_dim: int) -> bool:
    """Decide the arm count from the action width, falling back to name prefixes.

    The action width is the tightest signal (16 bimanual, 8 single); when it is
    absent or malformed, an arm-prefixed state name still reveals the layout.

    Args:
        state_names: The `observation.state` names.
        action_dim: The declared action width.

    Returns:
        (bool) True for the two-arm layout.
    """
    if action_dim == BIMANUAL_ACTION_DIM:
        return True
    if action_dim == SINGLE_ARM_ACTION_DIM:
        return False
    return any(name.startswith(_ARM_PREFIXES) for name in state_names)


def split_channel(name: str) -> tuple[str, Component | None]:
    """Split a state-channel name into its motor key and per-motor component.

    Args:
        name: A channel name such as `left_joint_1.torque`.

    Returns:
        (tuple[str, Component | None]) The motor key and its component; the
            component is `None` when the suffix is not one of the three contract
            suffixes.
    """
    dot = name.rfind(".")
    if dot == -1:
        return name, None
    joint, suffix = name[:dot], name[dot:]
    try:
        return joint, Component(suffix)
    except ValueError:
        return joint, None


def derive_observation_config(info_features: Mapping[str, Any]) -> ObservationConfig:
    """Read the observation configuration from an `info.json` feature map.

    `use_velocity_and_torque` and `state_dim` are both derived from `names`, never
    from `observation.state`'s shape (`10` FR-TRN-061).

    Args:
        info_features: The `features` map from `meta/info.json`.

    Returns:
        (ObservationConfig) The configuration the `names` array declares.
    """
    state_names = _state_names(info_features)
    action_names = _action_names(info_features)
    action_dim = len(action_names)
    return ObservationConfig(
        use_velocity_and_torque=any(name.endswith(TORQUE_SUFFIX) for name in state_names),
        state_dim=len(state_names),
        action_dim=action_dim,
        names=state_names,
        bimanual=_is_bimanual(state_names, action_dim),
    )


def _expected_names(effective_names: Sequence[str], bimanual: bool) -> tuple[str, ...]:
    """Return the canonical `observation.state` order the names should equal.

    The expected configuration is chosen by suffix presence, not by width: any
    `.vel`/`.torque` channel means the full per-motor layout is expected, so a
    partial strip (velocity kept, torque removed) is measured against the full
    layout and fails, rather than being quietly accepted as a smaller one.

    Args:
        effective_names: The post-rename channel names.
        bimanual: Whether the layout is two-arm.

    Returns:
        (tuple[str, ...]) The canonical names for the implied configuration.
    """
    implies_full = any(name.endswith((VELOCITY_SUFFIX, TORQUE_SUFFIX)) for name in effective_names)
    return observation_state_names(bimanual, implies_full)


def check_state_names(
    info_features: Mapping[str, Any], effective_names: Sequence[str], bimanual: bool
) -> tuple[PreflightFinding, ...]:
    """Verify the post-rename `observation.state` names against the canonical order.

    Two independent faults are reported:

    - a shape/`names` count disagreement (`shape[0] != len(names)`), which means
      one was edited without the other; and
    - the first position at which the names diverge from the canonical per-motor
      order, naming the joint and component that should sit there.

    The name comparison uses the DECLARED bimanual layout and the suffix-implied
    configuration, so both the rename rotation and the torque strip surface here.

    Args:
        info_features: The `features` map, read for the declared shape.
        effective_names: The `observation.state` names after any rename is applied.
        bimanual: Whether the layout is two-arm.

    Returns:
        (tuple[PreflightFinding, ...]) The located name/shape faults, empty when
            the names are exactly the canonical order and the shape agrees.
    """
    findings: list[PreflightFinding] = []

    body = info_features.get(OBSERVATION_STATE_KEY)
    if isinstance(body, Mapping):
        shape = body.get("shape", [])
        if isinstance(shape, Sequence) and len(shape) == 1:
            declared_width = shape[0]
            if isinstance(declared_width, int) and declared_width != len(effective_names):
                findings.append(
                    PreflightFinding(
                        code=PreflightCode.OBSERVATION_STATE_SHAPE_MISMATCH,
                        channel_name=OBSERVATION_STATE_KEY,
                        component=None,
                        joint=None,
                        detail=(
                            f"observation.state shape {declared_width} != "
                            f"{len(effective_names)} names; state_dim is derived from names, "
                            "so a shape that outlives its names is a stale or hand-edited width "
                            "(10 FR-TRN-061)"
                        ),
                    )
                )

    expected = _expected_names(effective_names, bimanual)
    if list(effective_names) == list(expected):
        return tuple(findings)

    for position in range(max(len(effective_names), len(expected))):
        want = expected[position] if position < len(expected) else None
        have = effective_names[position] if position < len(effective_names) else None
        if want == have:
            continue
        anchor = have if have is not None else want
        joint, component = split_channel(str(anchor))
        findings.append(
            PreflightFinding(
                code=PreflightCode.OBSERVATION_STATE_ORDER,
                channel_name=str(have) if have is not None else str(want),
                component=component,
                joint=joint,
                detail=(
                    f"observation.state names diverge at index {position}: expected "
                    f"{want!r}, got {have!r}. build_dataset_frame indexes by names order, "
                    "so this misalignment corrupts every channel from here with no exception "
                    "(10 FR-TRN-063)"
                ),
            )
        )
        break

    return tuple(findings)
