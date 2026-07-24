"""Per-episode signal series: `observation.state`, `action`, and the grid axis.

The viewer plots every state/action channel and the camera streams on one time
axis. That axis is the synthetic playback grid `timestamp = frame_index / fps`
(`FR-DAT-010`), which is exact for frame position and orthogonal to when a frame
was actually captured — `TimeAxis` carries `is_wall_clock = False` so the UI can
say so rather than let an operator read jitter into it.

Following error (`FR-DAT-012`) is computed here, on position channels only:
`observation.state[<motor>.pos] - action[<motor>.pos]`. `action` has no torque or
velocity dimension by `CTR-REC@v1`, so there is no torque following error to draw
and no "leader-measured torque" to mislabel.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyarrow.parquet as pq
from numpy.typing import NDArray

from backend.dataset.viewer.channels import (
    FollowingErrorPair,
    action_channel_names,
    following_error_pairs,
    state_channel_names,
    unit_for_channel,
)
from backend.dataset.viewer.constants import (
    ACTION_KEY,
    EPISODE_INDEX_COLUMN,
    FRAME_INDEX_COLUMN,
    OBSERVATION_STATE_KEY,
)
from backend.dataset.viewer.layout import DatasetLayout, DatasetLayoutError


@dataclass(frozen=True)
class TimeAxis:
    """The synthetic playback grid an episode is plotted against.

    Attributes:
        fps: Frames per second the grid is spaced on.
        frame_indices: The per-frame grid index, ascending from 0.
        timestamps: `frame_index / fps` in seconds — a grid coordinate, not a
            capture instant.
    """

    fps: int
    frame_indices: NDArray[np.int64]
    timestamps: NDArray[np.float64]

    # A grid coordinate is not wall-clock time; the UI must present it as such so
    # capture jitter is never read off this axis (`FR-DAT-010`, `02b` §5.2 ②).
    is_wall_clock: bool = False

    @property
    def domain_note(self) -> str:
        """A one-line UI note stating what this axis is (and is not)."""
        return "timestamp = frame_index / fps (synthetic grid coordinate, not capture time)"

    def frame_count(self) -> int:
        """The number of frames on the axis."""
        return int(self.frame_indices.shape[0])

    def index_at(self, seconds: float) -> int:
        """Return the frame index for a cursor time, by `round(t * fps)`.

        The grid is exact, so no interpolation is needed (`FR-DAT-014`); the
        result is clamped into the episode's frame range.

        Args:
            seconds: The cursor time in grid seconds.

        Returns:
            (int) The clamped frame index `round(seconds * fps)`.
        """
        raw = int(round(seconds * self.fps))
        last = self.frame_count() - 1
        return max(0, min(last, raw))


@dataclass(frozen=True)
class FollowingError:
    """Per-motor position following error, a data-quality signal.

    Attributes:
        motors: The motor keys, in `observation.state` position order.
        error: A `(frames, motors)` array of `state.pos - action.pos` in degrees.
    """

    motors: tuple[str, ...]
    error: NDArray[np.float64]

    # The channels this error is defined on — position only, by contract. Named so
    # a consumer cannot ask for a torque following error that does not exist.
    unit: str = "deg"


@dataclass(frozen=True)
class EpisodeSignals:
    """The state/action series of one episode on the shared grid axis.

    Attributes:
        time_axis: The synthetic grid the series are sampled on.
        state_names: `observation.state` channel names, matching `state` columns.
        action_names: `action` channel names, matching `action` columns.
        state: A `(frames, state_dim)` array of follower observations.
        action: A `(frames, action_dim)` array of leader position commands.
    """

    time_axis: TimeAxis
    state_names: tuple[str, ...]
    action_names: tuple[str, ...]
    state: NDArray[np.float64]
    action: NDArray[np.float64]

    def channel_series(self, name: str) -> tuple[NDArray[np.float64], str]:
        """Return one `observation.state` channel's values and its unit.

        Args:
            name: A channel name from `state_names`.

        Returns:
            (tuple) The channel's per-frame values and its display unit.

        Raises:
            KeyError: If the name is not an `observation.state` channel.
        """
        index = self.state_names.index(name) if name in self.state_names else None
        if index is None:
            raise KeyError(f"{name!r} is not an observation.state channel")
        return self.state[:, index], unit_for_channel(name)

    def following_error(self) -> FollowingError:
        """Compute per-motor position following error (`state.pos - action.pos`)."""
        pairs: tuple[FollowingErrorPair, ...] = following_error_pairs(
            {
                OBSERVATION_STATE_KEY: {"names": list(self.state_names)},
                ACTION_KEY: {"names": list(self.action_names)},
            }
        )
        if not pairs:
            empty = np.zeros((self.time_axis.frame_count(), 0), dtype=np.float64)
            return FollowingError(motors=(), error=empty)
        state_cols = [pair.state_index for pair in pairs]
        action_cols = [pair.action_index for pair in pairs]
        error = self.state[:, state_cols] - self.action[:, action_cols]
        return FollowingError(motors=tuple(pair.motor for pair in pairs), error=error)


def _vector_matrix(rows: list[object], width: int) -> NDArray[np.float64]:
    """Stack a parquet list-column into a `(frames, width)` float array.

    Args:
        rows: One list value per frame (each a vector of channel values).
        width: The expected channel count, from the feature `names`.

    Returns:
        (NDArray) The stacked matrix.

    Raises:
        DatasetLayoutError: If a row's width does not match the feature width.
    """
    matrix = np.zeros((len(rows), width), dtype=np.float64)
    for frame, value in enumerate(rows):
        vector = np.asarray(value, dtype=np.float64).reshape(-1)
        if vector.shape[0] != width:
            raise DatasetLayoutError(
                f"frame {frame} vector width {vector.shape[0]} != feature width {width}"
            )
        matrix[frame] = vector
    return matrix


def read_episode_signals(layout: DatasetLayout, episode_index: int) -> EpisodeSignals:
    """Read one episode's state/action series and grid axis from its data parquet.

    Rows are selected by the `episode_index` column, so a packed file holding
    several episodes yields exactly this episode, then ordered by `frame_index`.

    Args:
        layout: The dataset layout the episode belongs to.
        episode_index: The zero-based episode to read.

    Returns:
        (EpisodeSignals) The episode's state/action matrices on the grid axis.

    Raises:
        DatasetLayoutError: If the data parquet is unreadable or the episode has
            no rows.
    """
    location = layout.locate(episode_index)
    state_names = state_channel_names(layout.features)
    action_names = action_channel_names(layout.features)

    columns = [OBSERVATION_STATE_KEY, ACTION_KEY, FRAME_INDEX_COLUMN, EPISODE_INDEX_COLUMN]
    try:
        table = pq.read_table(location.data_file, columns=columns)
    except Exception as bad:  # noqa: BLE001 — any pyarrow read failure is a corrupt-file signal
        raise DatasetLayoutError(f"data parquet {location.data_file} is unreadable: {bad}") from bad

    data = table.to_pydict()
    episode_column = list(data.get(EPISODE_INDEX_COLUMN, []))
    all_frames = list(data.get(FRAME_INDEX_COLUMN, []))
    # Select this episode's rows by the episode_index column, so a packed file
    # holding several episodes is sliced without the global-index bookkeeping.
    selected = [i for i, ep in enumerate(episode_column) if int(ep) == episode_index]
    if not selected:
        raise DatasetLayoutError(f"episode {episode_index} has no rows in {location.data_file}")

    selected_frames = np.asarray([all_frames[i] for i in selected], dtype=np.int64)
    order = [selected[i] for i in np.argsort(selected_frames, kind="stable")]
    state_rows = [data[OBSERVATION_STATE_KEY][i] for i in order]
    action_rows = [data[ACTION_KEY][i] for i in order]
    ordered_frames = np.asarray([all_frames[i] for i in order], dtype=np.int64)

    state = _vector_matrix(state_rows, len(state_names))
    action = _vector_matrix(action_rows, len(action_names))
    timestamps = ordered_frames.astype(np.float64) / layout.fps
    time_axis = TimeAxis(fps=layout.fps, frame_indices=ordered_frames, timestamps=timestamps)

    return EpisodeSignals(
        time_axis=time_axis,
        state_names=state_names,
        action_names=action_names,
        state=state,
        action=action,
    )
