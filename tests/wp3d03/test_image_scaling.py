"""WP-3D-03 — image [0,1] scaling: RGB is divided by 255, depth keeps native units.

`02b` §8.1 WP-3D-03 lists image [0,1] scaling. It flows through
`compute_episode_stats` unchanged: an RGB channel is divided by 255 so its statistics
land in [0, 1], while a depth map (`is_depth_map`) skips the rescale and stays in its
stored units. The band asserts that convention rather than restating the factor.
"""

from __future__ import annotations

from pathlib import Path

import backend.dataset.stats as stats
from tests.wp3d03 import support

_RGB_VALUE = 128
_DEPTH_VALUE = 5000
_FRAMES = 4


def test_rgb_lands_in_unit_interval_depth_stays_native(tmp_path: Path) -> None:
    """RGB statistics are in [0, 1]; depth statistics keep their large native units."""
    feats = support.image_features(support.features())
    numeric = support.episode(0, frames=_FRAMES)
    episode = {
        "action": numeric["action"],
        "observation.state": numeric["observation.state"],
        support.RGB_KEY: support.write_rgb_images(tmp_path, _FRAMES, value=_RGB_VALUE),
        support.DEPTH_KEY: support.write_depth_images(tmp_path, _FRAMES, value=_DEPTH_VALUE),
    }

    result = stats.fit_normalization_stats([episode], feats)

    rgb = result.per_feature[support.RGB_KEY]
    assert float(rgb["min"].min()) >= stats.IMAGE_NORMALIZED_MIN
    assert float(rgb["max"].max()) <= stats.IMAGE_NORMALIZED_MAX
    assert abs(float(rgb["mean"].mean()) - _RGB_VALUE / 255.0) < 1e-3

    depth = result.per_feature[support.DEPTH_KEY]
    assert float(depth["max"].max()) > stats.IMAGE_NORMALIZED_MAX
    assert abs(float(depth["mean"].mean()) - _DEPTH_VALUE) < 1.0
