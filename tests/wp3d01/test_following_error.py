"""Acceptance ④/`FR-DAT-012`: following error is position-only, never torque.

Following error is `observation.state[<motor>.pos] - action[<motor>.pos]`, a
data-quality signal defined on position channels only. `action` is position-only
by `CTR-REC@v1`; a `.vel`/`.torque` name in `action` is the `07` §2.3.3 poison,
refused rather than displayed as a "leader-measured torque".
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.dataset.viewer import following_error_pairs
from backend.dataset.viewer.channels import ViewerChannelError, action_channel_names
from backend.dataset.viewer.constants import POSITION_SUFFIX
from backend.dataset.viewer.episode_viewer import EpisodeViewer


def test_pairs_are_position_channels_only(episode0: EpisodeViewer) -> None:
    features = {
        "observation.state": {"names": list(episode0.signals.state_names)},
        "action": {"names": list(episode0.signals.action_names)},
    }
    pairs = following_error_pairs(features)
    # One pair per action position channel; every paired channel is a .pos channel.
    assert len(pairs) == len(episode0.signals.action_names)
    for pair in pairs:
        assert episode0.signals.state_names[pair.state_index].endswith(POSITION_SUFFIX)
        assert episode0.signals.action_names[pair.action_index].endswith(POSITION_SUFFIX)


def test_following_error_equals_state_minus_action(episode0: EpisodeViewer) -> None:
    error = episode0.following_error()
    assert error.unit == "deg"
    assert error.error.shape[0] == episode0.time_axis.frame_count()
    # Recompute from the raw matrices via the name pairing and compare.
    state_names = episode0.signals.state_names
    action_names = episode0.signals.action_names
    for col, motor in enumerate(error.motors):
        s_idx = state_names.index(f"{motor}{POSITION_SUFFIX}")
        a_idx = action_names.index(f"{motor}{POSITION_SUFFIX}")
        expected = episode0.signals.state[:, s_idx] - episode0.signals.action[:, a_idx]
        assert np.allclose(error.error[:, col], expected)


def test_action_with_torque_is_refused() -> None:
    # A torque dimension smuggled into action is neither a robot command nor a
    # leader-measured torque; reading it must raise, not plot it.
    features = {"action": {"names": ["left_joint_1.pos", "left_joint_1.torque"]}}
    with pytest.raises(ViewerChannelError, match="position only"):
        action_channel_names(features)


def test_following_error_never_pairs_torque_or_velocity() -> None:
    # observation.state has torque/vel channels; none may enter following error.
    features = {
        "observation.state": {
            "names": ["j.pos", "j.vel", "j.torque"],
        },
        "action": {"names": ["j.pos"]},
    }
    pairs = following_error_pairs(features)
    assert len(pairs) == 1
    assert pairs[0].motor == "j"
