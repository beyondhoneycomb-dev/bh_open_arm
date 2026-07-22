"""A synthetic 48-dim dataset that stands in for a real recording.

`02b` §5.2 WP-3A-06 ③: the fixtures alone must let a 3B recorder or viewer test
run without a robot. This builder assembles one — the `CTR-REC@v1` feature set,
per-frame actions and observations from the dummy robot, per-frame images from
the synthetic camera, and the `CTR-CAP@v1` capture sidecar — and validates the
whole against the frozen recorder contract.

"48-dim" is the bimanual, velocity-and-torque `observation.state`: 16 motors ×
`(pos, vel, torque)`. The `action` stays position-only at 16. Every feature key,
name and width is derived from the frozen contracts; the camera slot identifier
round-trips across the CAM registry key, the CAP sidecar column, and the REC
image key, which is the join the whole barrier rests on (`02b` §5.0b row 1).
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.camera_registry import CameraSpec, make_arm_camera
from contracts.capture.schema import (
    CaptureSidecar,
    CaptureSidecarRow,
    SensorSample,
    SlotCapture,
    synthetic_grid_timestamp,
)
from contracts.fixtures.dummy_robot import DummyRobot
from contracts.fixtures.synthetic_camera import SyntheticCamera
from contracts.prim import REQUIRED_FRAME_TYPE, CameraSlotKey
from contracts.recorder import (
    RecorderConfig,
    action_names,
    feature_set,
    observation_state_names,
    validate_info_features,
)

# The fixture camera geometry. Small enough that a frame's bytes are cheap in a
# unit test, valid because width/height/fps are all specified so collection may
# start (`CTR-CAM@v1`). Not the real capture resolution — a fixture size.
FIXTURE_WIDTH = 8
FIXTURE_HEIGHT = 8
FIXTURE_FPS = 30

# The per-frame position ramp, in degrees. A deterministic, monotone command so
# the recorded action and the resulting observation both vary frame to frame.
_POSITION_STEP_DEG = 1.0

# The task a synthetic episode is labelled with; a single-task fixture uses 0.
_TASK_INDEX = 0


def default_camera_specs() -> tuple[CameraSpec, ...]:
    """Two configured per-arm RGB cameras, the default fixture camera set.

    Returns:
        (tuple[CameraSpec, ...]) `left_wrist` and `right_wrist`, RGB, configured.
    """
    capabilities = frozenset({REQUIRED_FRAME_TYPE})
    return tuple(
        make_arm_camera(side, "wrist", capabilities).configured(
            FIXTURE_WIDTH, FIXTURE_HEIGHT, FIXTURE_FPS
        )
        for side in ("left", "right")
    )


@dataclass(frozen=True)
class DatasetFrame:
    """One recorded frame of the synthetic dataset.

    Attributes:
        frame_index: The 0-based frame position, the sidecar/dataset join key.
        action: The position-only action, `<motor>.pos` -> degrees.
        observation_state: The interleaved `observation.state` vector.
        images: RGB (and depth) bytes per image feature key.
        meta: The five `CTR-REC@v1` meta features for this frame.
    """

    frame_index: int
    action: dict[str, float]
    observation_state: tuple[float, ...]
    images: dict[str, bytes]
    meta: dict[str, float]


@dataclass(frozen=True)
class SyntheticDataset:
    """A validated synthetic dataset: its feature set, frames and capture sidecar.

    Attributes:
        config: The recorder configuration the dataset was produced under.
        info_features: The `meta/info.json` feature set (`feature_set(config)`).
        frames: The per-frame records, in ascending frame order.
        sidecar: The per-episode capture-timestamp sidecar joined by `frame_index`.
    """

    config: RecorderConfig
    info_features: dict[str, dict[str, object]]
    frames: tuple[DatasetFrame, ...]
    sidecar: CaptureSidecar

    def observation_dim(self) -> int:
        """The `observation.state` width — 48 for a bimanual vel/torque dataset."""
        names = observation_state_names(self.config.bimanual, self.config.use_velocity_and_torque)
        return len(names)

    def validate(self) -> None:
        """Validate the dataset against `CTR-REC@v1` and the `CTR-CAP@v1` join.

        Raises:
            RecorderContractError: If the feature set carries an out-of-contract key
                or the action/state shapes are wrong.
            ValueError: If a frame's state width, image key set, or the sidecar join
                does not match the contracts.
        """
        validate_info_features(self.info_features, self.config)
        expected_state = observation_state_names(
            self.config.bimanual, self.config.use_velocity_and_torque
        )
        expected_images = {
            key for slot in self.config.camera_slots for key in _image_keys(slot, self.config)
        }
        sidecar_indices = {row.frame_index for row in self.sidecar.rows}
        for frame in self.frames:
            if len(frame.observation_state) != len(expected_state):
                raise ValueError(
                    f"frame {frame.frame_index} observation.state width "
                    f"{len(frame.observation_state)} != {len(expected_state)}"
                )
            if set(frame.images) != expected_images:
                raise ValueError(
                    f"frame {frame.frame_index} image keys {sorted(frame.images)} "
                    f"!= {sorted(expected_images)}"
                )
            if frame.frame_index not in sidecar_indices:
                raise ValueError(f"frame {frame.frame_index} has no capture sidecar row to join on")

    def info_json(self) -> dict[str, object]:
        """Render the `meta/info.json` shape a viewer reads channel names from.

        Returns:
            (dict[str, object]) `{features, fps, codebase_version}` — the closed
                feature set plus the synthetic-grid fps note.
        """
        return {
            "features": self.info_features,
            "fps": FIXTURE_FPS,
            "timestamp_is_synthetic_grid": True,
        }


def _image_keys(slot: CameraSlotKey, config: RecorderConfig) -> tuple[str, ...]:
    """The image feature keys a slot contributes (RGB, plus depth when a depth slot).

    Args:
        slot: The camera slot.
        config: The recorder configuration.

    Returns:
        (tuple[str, ...]) `observation.images.<slot>` and, for a depth slot, its depth key.
    """
    keys = [slot.image_key()]
    if slot in config.depth_slots:
        keys.append(slot.depth_key())
    return tuple(keys)


def build_synthetic_dataset(
    episode_index: int = 0,
    frame_count: int = 8,
    camera_specs: tuple[CameraSpec, ...] | None = None,
) -> SyntheticDataset:
    """Build and validate a synthetic bimanual 48-dim dataset.

    Args:
        episode_index: The episode the dataset records.
        frame_count: The number of frames to synthesize.
        camera_specs: The configured cameras to record; defaults to two arm RGB cameras.

    Returns:
        (SyntheticDataset) A validated dataset whose fixtures suffice for a 3B test.
    """
    specs = camera_specs if camera_specs is not None else default_camera_specs()
    slots = tuple(spec.slot for spec in specs)
    config = RecorderConfig(bimanual=True, use_velocity_and_torque=True, camera_slots=slots)
    info_features = feature_set(config)

    robot = DummyRobot(bimanual=True, use_velocity_and_torque=True)
    cameras = {spec.slot: SyntheticCamera(spec=spec) for spec in specs}
    names = action_names(config.bimanual)

    frames: list[DatasetFrame] = []
    sidecar_rows: list[CaptureSidecarRow] = []
    for frame_index in range(frame_count):
        action = {name: round(frame_index * _POSITION_STEP_DEG, 6) for name in names}
        observation = robot.step(action)
        images: dict[str, bytes] = {}
        row_slots: dict[CameraSlotKey, SlotCapture] = {}
        for slot, camera in cameras.items():
            frame = camera.read(frame_index)
            assert frame is not None  # the dataset builder injects no drops
            images[slot.image_key()] = frame.data
            row_slots[slot] = SlotCapture(
                capture_ts=frame.capture_ts,
                sensor=SensorSample(
                    sensor_ts_ns=frame.capture_ts.mono_ns, frame_number=frame_index
                ),
            )
        grid = synthetic_grid_timestamp(frame_index, FIXTURE_FPS)
        frames.append(
            DatasetFrame(
                frame_index=frame_index,
                action=dict(action),
                observation_state=tuple(observation["observation.state"]),  # type: ignore[arg-type]
                images=images,
                meta={
                    "timestamp": grid.seconds,
                    "frame_index": float(frame_index),
                    "episode_index": float(episode_index),
                    "index": float(episode_index * frame_count + frame_index),
                    "task_index": float(_TASK_INDEX),
                },
            )
        )
        sidecar_rows.append(CaptureSidecarRow(frame_index=frame_index, slots=row_slots))

    sidecar = CaptureSidecar(episode_index=episode_index, rows=tuple(sidecar_rows))
    dataset = SyntheticDataset(
        config=config, info_features=info_features, frames=tuple(frames), sidecar=sidecar
    )
    dataset.validate()
    return dataset
