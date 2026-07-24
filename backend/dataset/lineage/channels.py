"""The channel-selection state a training run consumed, tied to `CTR-REC@v1`.

`02b` §8.2 WP-3D-04 ③ requires the store to record which channels
(position / velocity / torque / depth) a training run actually fed the policy, and
to make that state *reproducible* — given a stored record, the exact
`observation.state` channel list the policy saw must be reconstructible.

This module derives that reconstruction from the recorder contract rather than
restating the channel grammar: the per-motor suffixes, the motor count and the
interleave order all come from `contracts.recorder` (`CTR-REC@v1`), so a channel
name here cannot fork one there. The consistency check it enforces — that the
stored `state_dim` is exactly the width `CTR-REC@v1` would produce for the recorded
selection — is what turns "channel selection is stored" into "channel selection is
verified", and it is what a later reproduction relies on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.dataset.lineage.constants import (
    CHANNEL_DEPTH,
    CHANNEL_POSITION,
    CHANNEL_TORQUE,
    CHANNEL_VELOCITY,
)
from contracts.recorder import (
    MOTORS_PER_ARM,
    POSITION_SUFFIX,
    TORQUE_SUFFIX,
    VELOCITY_SUFFIX,
    observation_state_names,
)


class ChannelSelectionError(ValueError):
    """Raised when a channel selection is internally inconsistent.

    The blocking cases (WP-3D-04 ③): a selection with no position channel, a
    velocity/torque channel selected on a dataset that did not record it, or a
    `state_dim` that is not the width `CTR-REC@v1` yields for the selection — any of
    which makes the recorded channel state impossible to reproduce faithfully.
    """


# The three per-motor suffixes that live inside the `observation.state` vector, in
# the interleave order `CTR-REC@v1` fixes. Depth is not here: it is an image feature
# (`observation.images.<slot>_depth`), so it never widens the state vector.
_STATE_SUFFIX_FOR_CHANNEL = {
    CHANNEL_POSITION: POSITION_SUFFIX,
    CHANNEL_VELOCITY: VELOCITY_SUFFIX,
    CHANNEL_TORQUE: TORQUE_SUFFIX,
}


@dataclass(frozen=True)
class ChannelSelection:
    """Which sensor channels a training run fed the policy as input.

    Attributes:
        pos: Whether the per-motor position channel was a training input. Position
            is the base observation; a selection without it is refused.
        vel: Whether the per-motor velocity channel was a training input. Only
            available when the dataset was recorded with `use_velocity_and_torque`.
        torque: Whether the per-motor torque channel was a training input. Same
            availability constraint as velocity.
        depth: Whether the depth image channel was a training input. Independent of
            the state width; recorded for reproducibility only.
    """

    pos: bool
    vel: bool
    torque: bool
    depth: bool

    def selected_state_suffixes(self) -> tuple[str, ...]:
        """Return the `observation.state` suffixes this selection includes, in order.

        Depth is excluded because it is not a state channel.

        Returns:
            (tuple[str, ...]) A subset of `(.pos, .vel, .torque)`, contract order.
        """
        chosen = {
            CHANNEL_POSITION: self.pos,
            CHANNEL_VELOCITY: self.vel,
            CHANNEL_TORQUE: self.torque,
        }
        return tuple(
            _STATE_SUFFIX_FOR_CHANNEL[channel]
            for channel in (CHANNEL_POSITION, CHANNEL_VELOCITY, CHANNEL_TORQUE)
            if chosen[channel]
        )

    def motor_channel_count(self) -> int:
        """The number of per-motor state channels this selection includes.

        Returns:
            (int) 1, 2 or 3 — the count of `.pos`/`.vel`/`.torque` selected.
        """
        return len(self.selected_state_suffixes())

    def validate(self, use_velocity_and_torque: bool, state_dim: int) -> None:
        """Refuse a selection that cannot have produced the recorded state width.

        Ties the selection to `CTR-REC@v1`: position must be present; velocity and
        torque may be selected only when the dataset recorded them; and `state_dim`
        must factor as `motors * motor_channel_count` with a motor count of one or
        two arms. A record that fails this is not reproducible, so the store refuses
        it (a silent inconsistency here is a missing/false lineage mapping).

        Args:
            use_velocity_and_torque: The dataset's recorder switch — whether the
                velocity and torque channels exist to be selected at all.
            state_dim: The `observation.state` width the run consumed.

        Raises:
            ChannelSelectionError: On a positionless selection, a velocity/torque
                selection the dataset never recorded, or a `state_dim` that is not a
                valid single- or bimanual `CTR-REC@v1` width for the selection.
        """
        if not self.pos:
            raise ChannelSelectionError(
                "channel selection has no position channel; position is the base "
                "observation and every recorded state carries it"
            )
        if (self.vel or self.torque) and not use_velocity_and_torque:
            raise ChannelSelectionError(
                "velocity/torque channel selected on a dataset recorded with "
                "use_velocity_and_torque=False; that data was never written"
            )
        motor_channels = self.motor_channel_count()
        if state_dim <= 0 or state_dim % motor_channels != 0:
            raise ChannelSelectionError(
                f"state_dim {state_dim} is not a multiple of the {motor_channels} selected "
                "per-motor channels; the selection cannot have produced this width"
            )
        motors = state_dim // motor_channels
        if motors not in (MOTORS_PER_ARM, MOTORS_PER_ARM * 2):
            raise ChannelSelectionError(
                f"state_dim {state_dim} implies {motors} motors, which is neither one arm "
                f"({MOTORS_PER_ARM}) nor two ({MOTORS_PER_ARM * 2}) under CTR-REC@v1"
            )

    def reproduce_state_channels(
        self, use_velocity_and_torque: bool, state_dim: int
    ) -> tuple[str, ...]:
        """Reconstruct the exact `observation.state` channel names the policy saw.

        This is the ③ reproducibility guarantee: from the stored selection and the
        recorded width, regenerate the channel list off `CTR-REC@v1` and confirm its
        length is the stored `state_dim`. The bimanual flag is derived from the width
        rather than stored, since `CTR-REC@v1` fixes the motor count.

        Args:
            use_velocity_and_torque: The dataset's recorder switch.
            state_dim: The recorded `observation.state` width.

        Returns:
            (tuple[str, ...]) The interleaved channel names the run consumed, a subset
                of the dataset's `observation.state` names in contract order.

        Raises:
            ChannelSelectionError: If the selection is inconsistent with the width.
        """
        self.validate(use_velocity_and_torque, state_dim)
        motors = state_dim // self.motor_channel_count()
        bimanual = motors == MOTORS_PER_ARM * 2
        suffixes = self.selected_state_suffixes()
        names = tuple(
            name
            for name in observation_state_names(bimanual, use_velocity_and_torque)
            if name.endswith(suffixes)
        )
        if len(names) != state_dim:
            raise ChannelSelectionError(
                f"reproduced {len(names)} channels but state_dim is {state_dim}; the stored "
                "selection does not match the recorded width"
            )
        return names

    def to_json(self) -> str:
        """Serialise deterministically for the `channel_selection` column.

        Returns:
            (str) Sorted-key JSON of the four channel booleans.
        """
        return json.dumps(
            {
                CHANNEL_POSITION: self.pos,
                CHANNEL_VELOCITY: self.vel,
                CHANNEL_TORQUE: self.torque,
                CHANNEL_DEPTH: self.depth,
            },
            sort_keys=True,
        )

    @staticmethod
    def from_json(text: str) -> ChannelSelection:
        """Rebuild a selection from its stored JSON.

        Args:
            text: The `channel_selection` column value written by `to_json`.

        Returns:
            (ChannelSelection) The reconstructed selection.

        Raises:
            ChannelSelectionError: When a required channel key is absent.
        """
        raw: dict[str, Any] = json.loads(text)
        try:
            return ChannelSelection(
                pos=bool(raw[CHANNEL_POSITION]),
                vel=bool(raw[CHANNEL_VELOCITY]),
                torque=bool(raw[CHANNEL_TORQUE]),
                depth=bool(raw[CHANNEL_DEPTH]),
            )
        except KeyError as missing:
            raise ChannelSelectionError(
                f"channel_selection JSON is missing key {missing}"
            ) from missing
