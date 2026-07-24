"""WP-3D-04 ③: the channel-selection state is stored and is reproducible.

The store must record which channels (pos/vel/torque/depth) a run fed the policy
and let the exact `observation.state` channel list be reconstructed off
`CTR-REC@v1`. These tests hold the round-trip through the database and the
consistency checks that make a selection reproducible rather than merely stored.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.dataset.lineage import (
    ChannelSelection,
    ChannelSelectionError,
    LineageError,
    LineageStore,
)
from backend.dataset.lineage.constants import MEMORY_DATABASE
from contracts.recorder import (
    POSITION_SUFFIX,
    TORQUE_SUFFIX,
    VELOCITY_SUFFIX,
    observation_state_names,
)
from tests.wp3d04._support import fixture_record


def test_full_selection_reproduces_the_48_dim_state_off_the_contract() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        record = fixture_record((0,), "/runs/a", 1000)
        store.record(record)
        restored = store.get("/runs/a", 1000)
        assert restored is not None
        assert restored.channels == record.channels

        names = restored.channels.reproduce_state_channels(
            restored.use_velocity_and_torque, restored.state_dim
        )
        assert names == observation_state_names(bimanual=True, use_velocity_and_torque=True)
        assert len(names) == restored.state_dim


def test_position_only_selection_reproduces_only_pos_channels() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        pos_only = ChannelSelection(pos=True, vel=False, torque=False, depth=False)
        # The dataset recorded vel/torque, but this run consumed position only: width 16.
        record = fixture_record((0,), "/runs/a", 1000, channels=pos_only, state_dim=16)
        store.record(record)

        restored = store.get("/runs/a", 1000)
        assert restored is not None
        names = restored.channels.reproduce_state_channels(True, 16)
        assert len(names) == 16
        assert all(name.endswith(POSITION_SUFFIX) for name in names)
        assert not any(name.endswith((VELOCITY_SUFFIX, TORQUE_SUFFIX)) for name in names)


def test_a_positionless_selection_is_refused() -> None:
    with pytest.raises(ChannelSelectionError, match="no position"):
        ChannelSelection(pos=False, vel=True, torque=False, depth=False).validate(True, 16)


def test_velocity_without_the_recorder_switch_is_refused() -> None:
    selection = ChannelSelection(pos=True, vel=True, torque=False, depth=False)
    with pytest.raises(ChannelSelectionError, match="use_velocity_and_torque=False"):
        selection.validate(False, 16)


def test_a_state_dim_the_selection_cannot_produce_is_refused() -> None:
    # Position only implies motors == state_dim; 48 is neither one arm nor two.
    pos_only = ChannelSelection(pos=True, vel=False, torque=False, depth=False)
    with pytest.raises(ChannelSelectionError):
        pos_only.validate(True, 48)


def test_record_refuses_a_selection_inconsistent_with_its_width() -> None:
    bad = dataclasses.replace(
        fixture_record((0,), "/runs/a", 1000),
        channels=ChannelSelection(pos=True, vel=False, torque=False, depth=False),
        state_dim=48,
    )
    with LineageStore(MEMORY_DATABASE) as store, pytest.raises(LineageError):
        store.record(bad)


def test_channel_selection_json_round_trips() -> None:
    selection = ChannelSelection(pos=True, vel=False, torque=True, depth=True)
    assert ChannelSelection.from_json(selection.to_json()) == selection
