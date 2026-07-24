"""Lineage records grounded in the synthetic dataset fixture (WP-3D-04 tests).

`THE ONE RULE` for this band: the offline acceptance is built on the synthetic
dataset fixture, not on a mock. So these helpers assemble a `LineageRecord` from a
real `build_synthetic_dataset()` — its content hash is a digest of the fixture's
actual `info.json` and frames, its `state_dim` and `use_velocity_and_torque` come
from the fixture's `CTR-REC@v1` config, and its stamped `repo_id` is produced by the
recorder's own `stamp_repo_id` (reused, not forked). A record built this way is the
lineage of a checkpoint that trained on that fixture.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from backend.dataset.lineage import ChannelSelection, LineageRecord
from backend.recorder.embed import stamp_repo_id
from contracts.fixtures.synthetic_dataset import SyntheticDataset, build_synthetic_dataset

# A fixed stamp instant so a fixture `repo_id` is deterministic across runs; the
# value only has to be a valid moment for the recorder's stamp format.
_STAMP_MOMENT = datetime(2026, 7, 23, 10, 0, 0)
_BASE_REPO_ID = "openarm/pick_place"


def fixture_content_hash(dataset: SyntheticDataset) -> str:
    """Digest a synthetic dataset's info and frames into a stable content hash.

    Args:
        dataset: The synthetic dataset to hash.

    Returns:
        (str) A hex sha256 over the fixture's `info.json` and every frame's action,
            observation and image bytes — a stand-in for the real dataset content hash.
    """
    digest = hashlib.sha256()
    digest.update(json.dumps(dataset.info_json(), sort_keys=True).encode("utf-8"))
    for frame in dataset.frames:
        digest.update(json.dumps(frame.action, sort_keys=True).encode("utf-8"))
        digest.update(json.dumps(list(frame.observation_state)).encode("utf-8"))
        for key in sorted(frame.images):
            digest.update(key.encode("utf-8"))
            digest.update(frame.images[key])
    return digest.hexdigest()


def fixture_repo_id() -> str:
    """The stamped `repo_id` used across the fixture records, from the recorder stamp."""
    return stamp_repo_id(_BASE_REPO_ID, _STAMP_MOMENT)


def full_channel_selection() -> ChannelSelection:
    """The selection matching the fixture's 48-dim velocity-and-torque state."""
    return ChannelSelection(pos=True, vel=True, torque=True, depth=False)


def fixture_record(
    episodes: tuple[int, ...],
    output_dir: str,
    step: int,
    content_hash: str | None = None,
    channels: ChannelSelection | None = None,
    state_dim: int | None = None,
    stats_hash: str = "stats-0000",
    revision: str = "rev-0001",
) -> LineageRecord:
    """Build a lineage record for a checkpoint trained on the synthetic fixture.

    Args:
        episodes: The episode indices the checkpoint consumed.
        output_dir: The training run's output directory.
        step: The checkpoint step.
        content_hash: The dataset content hash; defaults to the fixture's own.
        channels: The channel selection; defaults to the full 48-dim selection.
        state_dim: The state width; defaults to the fixture's observation dim.
        stats_hash: The normalisation-statistics hash to record.
        revision: The dataset revision to record.

    Returns:
        (LineageRecord) A record whose dataset identity is the synthetic fixture.
    """
    dataset = build_synthetic_dataset()
    selection = channels if channels is not None else full_channel_selection()
    return LineageRecord(
        repo_id=fixture_repo_id(),
        dataset_content_hash=content_hash
        if content_hash is not None
        else fixture_content_hash(dataset),
        revision=revision,
        episodes=episodes,
        stats_hash=stats_hash,
        use_velocity_and_torque=dataset.config.use_velocity_and_torque,
        state_dim=state_dim if state_dim is not None else dataset.observation_dim(),
        encoder_settings={"vcodec": "libx264", "pix_fmt": "yuv420p"},
        channels=selection,
        output_dir=output_dir,
        step=step,
    )
