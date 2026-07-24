"""`FR-DAT-013`: joint-limit / torque-tmax overlays with near-saturation highlighting.

The overlay highlights where a channel is near or past a bound, and keeps the
mechanical limit (URDF canon) distinct from the soft clamp (follower config). The
three Damiao torque limits are the documented reference the torque overlay uses.
"""

from __future__ import annotations

import numpy as np

from backend.dataset.viewer import (
    DAMIAO_TMAX_NM,
    LimitBand,
    LimitKind,
    annotate_channel,
    torque_band,
)
from backend.dataset.viewer.episode_viewer import EpisodeViewer


def test_damiao_tmax_reference() -> None:
    assert DAMIAO_TMAX_NM == {"DM8009": 54.0, "DM4340": 28.0, "DM4310": 10.0}


def test_torque_band_is_symmetric_and_mechanical() -> None:
    band = torque_band(10.0)
    assert band.lower == -10.0
    assert band.upper == 10.0
    assert band.kind == LimitKind.MECHANICAL


def test_near_and_saturation_masks() -> None:
    series = np.array([0.0, 9.0, 9.5, 10.0, 11.0, -10.0])
    annotation = annotate_channel(series, (torque_band(10.0),))
    (band,) = annotation.bands
    # At or beyond +/-10 is saturated; within 90% of the bound is near.
    assert band.saturated_frames() == (3, 4, 5)
    assert band.near_frames() == (1, 2)


def test_mechanical_and_soft_clamp_kept_distinct() -> None:
    # A joint carries both a hard mechanical limit and a tighter soft clamp; the
    # overlay must label them apart, not merge them.
    series = np.array([0.0, 8.0, 9.5])
    mechanical = LimitBand(lower=-10.0, upper=10.0, kind=LimitKind.MECHANICAL)
    soft = LimitBand(lower=-9.0, upper=9.0, kind=LimitKind.SOFT_CLAMP)
    annotation = annotate_channel(series, (mechanical, soft))
    kinds = [band.kind for band in annotation.bands]
    assert kinds == [LimitKind.MECHANICAL, LimitKind.SOFT_CLAMP]
    # 9.5 is inside the mechanical band but past the soft clamp.
    mech_band, soft_band = annotation.bands
    assert 2 not in mech_band.saturated_frames()
    assert 2 in soft_band.saturated_frames()


def test_viewer_overlay_annotates_named_channels(episode0: EpisodeViewer) -> None:
    torque_channels = [n for n in episode0.signals.state_names if n.endswith(".torque")]
    assert torque_channels
    spec = {name: (torque_band(10.0),) for name in torque_channels}
    annotations = episode0.overlay(spec)
    # Only the specified channels are annotated, and each carries its band.
    assert set(annotations) == set(torque_channels)
    for name in torque_channels:
        assert annotations[name].bands[0].kind == LimitKind.MECHANICAL


def test_degenerate_band_rejected() -> None:
    try:
        LimitBand(lower=5.0, upper=5.0, kind=LimitKind.MECHANICAL)
    except ValueError:
        return
    raise AssertionError("a degenerate band (upper <= lower) must be rejected")
