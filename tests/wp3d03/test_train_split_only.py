"""WP-3D-03 ① — train-split-only fit; split-local statistics are diagnostic only.

`02b` §8.2 WP-3D-03: normalization statistics fit on the TRAIN split only and apply
identically to val/test/inference; a per-split re-fit is validation leakage and
FAIL_BLOCKING. Two guards are exercised here: the fit refuses to produce normalization
from a non-train split, and the static check forbids a diagnostic (split-local) value
from reaching a normalization input.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import backend.dataset.stats as stats
from tests.wp3d03 import support

_STATS_TREE = Path(__file__).resolve().parents[2] / "backend" / "dataset" / "stats"

# A leak via a name bound to a diagnostic producer, then handed to the normalizer.
_LEAK_VIA_NAME = """
from backend.dataset.stats.fit import compute_diagnostic_stats
from backend.dataset.stats.normalize import build_normalizer, NormalizationMode


def leak(episodes, features):
    diagnostic = compute_diagnostic_stats(episodes, features, "val")
    return build_normalizer(diagnostic, NormalizationMode.MEAN_STD)
"""

# A leak via a `.diagnostics` access handed straight to the normalizer.
_LEAK_VIA_ATTR = """
from backend.dataset.stats.normalize import build_normalizer, NormalizationMode


def leak(fitted):
    return build_normalizer(fitted.diagnostics["val"], NormalizationMode.MEAN_STD)
"""

# The correct wiring: the normalizer is built from the train normalization.
_CLEAN = """
from backend.dataset.stats.normalize import build_normalizer, NormalizationMode


def ok(fitted):
    return build_normalizer(fitted.normalization, NormalizationMode.MEAN_STD)
"""


def test_fit_dataset_stats_normalizes_from_train_only() -> None:
    """Only the train split feeds normalization; val/test yield diagnostics."""
    feats = support.features()
    episodes_by_split = {
        "train": [support.episode(index) for index in range(3)],
        "val": [support.episode(100)],
        "test": [support.episode(200)],
    }
    fitted = stats.fit_dataset_stats(episodes_by_split, feats)

    assert isinstance(fitted.normalization, stats.NormalizationStats)
    assert set(fitted.diagnostics) == {"val", "test"}
    for diagnostic in fitted.diagnostics.values():
        assert isinstance(diagnostic, stats.DiagnosticStats)
        assert not isinstance(diagnostic, stats.NormalizationStats)


def test_normalization_ignores_val_test_contents() -> None:
    """Changing val/test data leaves the train normalization identical (no leakage)."""
    feats = support.features()
    train = [support.episode(index) for index in range(3)]

    with_val_a = stats.fit_dataset_stats(
        {"train": list(train), "val": [support.episode(50)]}, feats
    )
    with_val_b = stats.fit_dataset_stats(
        {"train": list(train), "val": [support.episode(999)]}, feats
    )

    assert stats.stats_content_hash(with_val_a.normalization) == stats.stats_content_hash(
        with_val_b.normalization
    )


def test_fit_normalization_on_non_train_split_is_leakage() -> None:
    """Producing normalization from a non-train split is refused as leakage."""
    feats = support.features()
    with pytest.raises(stats.LeakageError):
        stats.fit_normalization_stats(support.episode_generator(2), feats, split="val")


def test_diagnostic_on_train_split_is_refused() -> None:
    """The train split normalizes; asking for it as a diagnostic is refused."""
    feats = support.features()
    with pytest.raises(stats.LeakageError):
        stats.compute_diagnostic_stats(support.episode_generator(2), feats, "train")


def test_fit_dataset_stats_requires_a_train_split() -> None:
    """A dataset with no train split cannot be fit."""
    feats = support.features()
    with pytest.raises(KeyError):
        stats.fit_dataset_stats({"val": [support.episode(0)]}, feats)


def test_owned_tree_has_no_diagnostic_to_normalization_flow() -> None:
    """The static check finds no diagnostic value reaching a normalization input."""
    assert stats.scan_tree(_STATS_TREE) == []


def test_static_check_catches_a_diagnostic_normalization_leak() -> None:
    """The static check bites: a diagnostic fed to the normalizer is a finding."""
    via_name = stats.scan_source(Path("leak_via_name.py"), _LEAK_VIA_NAME)
    via_attr = stats.scan_source(Path("leak_via_attr.py"), _LEAK_VIA_ATTR)
    clean = stats.scan_source(Path("clean.py"), _CLEAN)

    assert len(via_name) == 1
    assert len(via_attr) == 1
    assert clean == []
