"""RUNS ⑤ — the One Euro pose smoother reduces jitter without biasing the pose.

`FR-TEL-039`: One Euro smoothing (adaptive-cutoff position, SLERP rotation) is applied
to the target pose. A stationary noisy input must come out markedly less jittery, the
smoothed pose must stay centred on the true pose (no lag bias at rest), and the first
post-construction sample must pass through unchanged.
"""

from __future__ import annotations

import numpy as np

from backend.teleop.clutch import OneEuroPoseSmoother
from backend.teleop.clutch.rotation import angle_between, quat_normalize

_FPS = 60
_FRAME_S = 1.0 / _FPS
_FRAMES = 120
_BASE_POSITION = np.array([0.5, -0.3, 0.2])
_IDENTITY = np.array([0.0, 0.0, 0.0, 1.0])
_POSITION_NOISE_STD = 0.02
_ANGLE_NOISE_STD = 0.05


def _mean_successive_position_jitter(track: list[np.ndarray]) -> float:
    """Mean L2 frame-to-frame movement of a position track (its jitter)."""
    diffs = [float(np.linalg.norm(track[i] - track[i - 1])) for i in range(1, len(track))]
    return float(np.mean(diffs))


def _mean_successive_angular_jitter(track: list[np.ndarray]) -> float:
    """Mean frame-to-frame rotation of a quaternion track (its angular jitter)."""
    diffs = [angle_between(track[i], track[i - 1]) for i in range(1, len(track))]
    return float(np.mean(diffs))


def _small_rotation(rng: np.random.Generator) -> np.ndarray:
    """A random small rotation quaternion about a random axis (jitter around identity)."""
    axis = rng.normal(size=3)
    axis = axis / np.linalg.norm(axis)
    angle = rng.normal(0.0, _ANGLE_NOISE_STD)
    return np.array([*(axis * np.sin(angle / 2.0)), np.cos(angle / 2.0)])


def test_first_sample_passes_through() -> None:
    """The first sample after construction is emitted unchanged (no cold-start distortion)."""
    smoother = OneEuroPoseSmoother()
    position = np.array([0.1, 0.2, 0.3])
    quaternion = quat_normalize(np.array([0.0, 0.3, 0.0, 0.95]))
    out = smoother.filter(position, quaternion, 0.0)
    assert np.allclose(out.position, position)
    assert np.allclose(out.quaternion, quaternion)


def test_position_jitter_is_reduced() -> None:
    """A stationary noisy position stream comes out with much smaller frame-to-frame jitter."""
    rng = np.random.default_rng(20260723)
    raw: list[np.ndarray] = []
    smoothed: list[np.ndarray] = []
    smoother = OneEuroPoseSmoother()
    for frame in range(_FRAMES):
        sample = _BASE_POSITION + rng.normal(0.0, _POSITION_NOISE_STD, size=3)
        raw.append(sample)
        smoothed.append(smoother.filter(sample, _IDENTITY, frame * _FRAME_S).position)

    raw_jitter = _mean_successive_position_jitter(raw)
    smoothed_jitter = _mean_successive_position_jitter(smoothed)
    assert smoothed_jitter < 0.5 * raw_jitter


def test_no_steady_state_bias() -> None:
    """At rest the smoothed pose stays centred on the true pose (no lasting offset)."""
    rng = np.random.default_rng(7)
    smoother = OneEuroPoseSmoother()
    tail: list[np.ndarray] = []
    for frame in range(_FRAMES):
        sample = _BASE_POSITION + rng.normal(0.0, _POSITION_NOISE_STD, size=3)
        out = smoother.filter(sample, _IDENTITY, frame * _FRAME_S)
        if frame >= _FRAMES - 30:
            tail.append(out.position)

    settled = np.mean(np.stack(tail), axis=0)
    assert np.allclose(settled, _BASE_POSITION, atol=3 * _POSITION_NOISE_STD)


def test_rotation_jitter_is_reduced() -> None:
    """A jittery orientation stream comes out with smaller frame-to-frame rotation."""
    rng = np.random.default_rng(101)
    raw: list[np.ndarray] = []
    smoothed: list[np.ndarray] = []
    smoother = OneEuroPoseSmoother()
    for frame in range(_FRAMES):
        quat = _small_rotation(rng)
        raw.append(quat)
        smoothed.append(smoother.filter(_BASE_POSITION, quat, frame * _FRAME_S).quaternion)

    assert _mean_successive_angular_jitter(smoothed) < 0.5 * _mean_successive_angular_jitter(raw)
