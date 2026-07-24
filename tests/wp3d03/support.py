"""Shared builders for the WP-3D-03 statistics tests.

The synthetic dataset (`contracts.fixtures.synthetic_dataset`) is this band's
stand-in for a real recording (`02b` §5.2 WP-3A-06); these helpers turn it into the
`compute_episode_stats` inputs the fit consumes, build the on-disk image fixtures the
[0,1]-scaling test needs, and track how many episodes a streaming fit holds alive.
"""

from __future__ import annotations

import weakref
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from backend.dataset.stats.episodes import numeric_episode_data, numeric_features, numeric_names
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset
from contracts.recorder import ACTION_KEY, OBSERVATION_STATE_KEY

DEFAULT_FRAMES = 12

RGB_KEY = "observation.images.rgb"
DEPTH_KEY = "observation.images.depth"


def features() -> dict[str, dict[str, object]]:
    """The numeric `action`/`observation.state` feature description for the fixture."""
    return numeric_features(build_synthetic_dataset(0, DEFAULT_FRAMES).config)


def names() -> dict[str, tuple[str, ...]]:
    """The per-feature channel names for the fixture."""
    return numeric_names(build_synthetic_dataset(0, DEFAULT_FRAMES).config)


def episode(index: int, frames: int = DEFAULT_FRAMES) -> dict[str, np.ndarray]:
    """One synthetic episode's numeric `compute_episode_stats` input."""
    return numeric_episode_data(build_synthetic_dataset(index, frames))


def episode_generator(count: int, frames: int = DEFAULT_FRAMES, start: int = 0) -> Iterator[dict]:
    """Yield `count` synthetic episodes lazily, building each on demand."""
    for offset in range(count):
        yield episode(start + offset, frames)


def concat_values(episodes: Sequence[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    """Concatenate episodes' per-feature frames, for the exact-quantile report."""
    return {
        ACTION_KEY: np.concatenate([e[ACTION_KEY] for e in episodes], axis=0),
        OBSERVATION_STATE_KEY: np.concatenate([e[OBSERVATION_STATE_KEY] for e in episodes], axis=0),
    }


class _TrackedEpisode(dict):
    """A dict subclass so an episode can hold a weak reference for liveness tracking.

    A plain dict has no `__weakref__` slot; the subclass adds one without changing how
    the fit consumes it (it is still a mapping, and `compute_episode_stats` copies it).
    """


class LiveEpisodeTracker:
    """Track how many wrapped episode dicts are alive at once.

    A streaming fit holds one episode at a time, so `max_live` stays at one (two with
    GC slack); a fit that first collects every episode drives it to the episode count.
    Relies on CPython refcounting: when the fit's loop rebinds, the previous episode's
    only reference drops and its finalizer runs immediately.
    """

    def __init__(self) -> None:
        self.live = 0
        self.max_live = 0

    def wrap(self, data: dict) -> dict:
        """Register one episode dict and return a weakref-trackable copy."""
        tracked = _TrackedEpisode(data)
        self.live += 1
        self.max_live = max(self.max_live, self.live)
        weakref.finalize(tracked, self._release)
        return tracked

    def _release(self) -> None:
        """Drop the live count when a wrapped episode is collected."""
        self.live -= 1


def write_rgb_images(directory: Path, count: int, value: int = 128, size: int = 8) -> list[str]:
    """Write `count` uint8 RGB PNGs of a constant value; return their paths."""
    paths: list[str] = []
    for index in range(count):
        array = np.full((size, size, 3), value, dtype=np.uint8)
        path = directory / f"rgb_{index}.png"
        Image.fromarray(array).save(path)
        paths.append(str(path))
    return paths


def write_depth_images(directory: Path, count: int, value: int = 5000, size: int = 8) -> list[str]:
    """Write `count` uint16 depth TIFFs of a constant value; return their paths."""
    paths: list[str] = []
    for index in range(count):
        array = np.full((size, size), value, dtype=np.uint16)
        path = directory / f"depth_{index}.tiff"
        Image.fromarray(array).save(path)
        paths.append(str(path))
    return paths


def image_features(
    base: dict[str, dict[str, object]], size: int = 8
) -> dict[str, dict[str, object]]:
    """Extend a numeric feature description with an RGB and a depth image feature."""
    feats = dict(base)
    feats[RGB_KEY] = {
        "dtype": "image",
        "shape": (3, size, size),
        "names": ["c", "h", "w"],
        "info": {},
    }
    feats[DEPTH_KEY] = {
        "dtype": "image",
        "shape": (1, size, size),
        "names": ["c", "h", "w"],
        "info": {"is_depth_map": True},
    }
    return feats
