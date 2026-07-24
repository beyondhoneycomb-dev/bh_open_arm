"""Shared fixtures for the WP-3D-07 import/export tests.

The acceptance is built on the `WP-3A-06` synthetic dataset fixture (`02b` batch
rule): the native schema and the good timestamp grid are derived from a real synthetic
recording, and the imported artifact is the legacy-schema counterpart. This keeps the
tests exercising the frozen `CTR-REC@v1` contract rather than hand-written constants.
"""

from __future__ import annotations

from backend.dataset.import_export import (
    ImportedDataset,
    SchemaFacts,
    legacy_import_schema_facts,
    native_schema_facts,
)
from contracts.fixtures.synthetic_dataset import (
    FIXTURE_FPS,
    SyntheticDataset,
    build_synthetic_dataset,
)
from contracts.recorder import RecorderConfig

FRAME_COUNT = 8


def synthetic() -> SyntheticDataset:
    """Build the bimanual synthetic dataset used as the native reference recording."""
    return build_synthetic_dataset(episode_index=0, frame_count=FRAME_COUNT)


def native_facts() -> SchemaFacts:
    """Native schema facts derived from the synthetic dataset's recorder config."""
    dataset = synthetic()
    return native_schema_facts(dataset.config, fps=FIXTURE_FPS)


def single_arm_native_facts() -> SchemaFacts:
    """Native single-arm schema facts, for the crisp `joint_1` vs `joint1` name diff."""
    config = RecorderConfig(bimanual=False, use_velocity_and_torque=False)
    return native_schema_facts(config, fps=FIXTURE_FPS)


def fixture_timestamps() -> tuple[float, ...]:
    """The synthetic dataset's per-frame `timestamp` grid (`frame_index / fps`)."""
    dataset = synthetic()
    return tuple(float(frame.meta["timestamp"]) for frame in dataset.frames)


def imported_dataset() -> ImportedDataset:
    """A legacy-imported artifact with a valid timestamp grid."""
    return ImportedDataset(
        schema=legacy_import_schema_facts(fps=FIXTURE_FPS),
        timestamps=fixture_timestamps(),
    )


def jittered_timestamps() -> tuple[float, ...]:
    """The fixture grid with one gap pushed well outside `1/fps ± 1e-4`."""
    grid = list(fixture_timestamps())
    grid[3] += 0.02
    return tuple(grid)


def broken_imported_dataset() -> ImportedDataset:
    """A legacy-imported artifact whose timestamp grid fails load validation."""
    return ImportedDataset(
        schema=legacy_import_schema_facts(fps=FIXTURE_FPS),
        timestamps=jittered_timestamps(),
    )
