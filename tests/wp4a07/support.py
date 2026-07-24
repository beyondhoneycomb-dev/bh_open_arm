"""Builders that ground the WP-4A-07 gates on the committed dummy robot + a fixture policy.

`THE ONE RULE` for this band: the offline acceptance rides on the committed upstream —
the `ActuationScheduler`/mailbox (Wave 0-A), the `DummyOpenArmRobot` (Wave 0-Ops), and
the `LineageRecord` (WP-4A-05) — not on mocks. The one thing standing in for hardware
is the *policy*: there is no committed trained checkpoint, so `FixturePolicy` is a
deterministic, torch-free `ChunkPolicy` that emits reproducible 16-wide actions. Every
other object here is the real committed type.

`ConnectCountingRobot` is the only subclass, and it exists solely to make the
switch-keeps-connection invariant (CG-4A-07e) measurable: it counts `connect()` and
`disconnect()` so a test can assert the count does not move across 100 backend switches.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.inference.adapter import PolicyProfile
from backend.training.lineage import (
    CONTAINER_NOT_USED,
    DatasetLineage,
    LineageRecord,
    MergeHistoryEntry,
    ObservationConfig,
    VersionPins,
)
from contracts.action import BIMANUAL_ACTION_DIM
from packages.lerobot_robot_openarm_dummy import DummyOpenArmRobot, DummyRobotConfig

# Fixture-policy chunk length. Kept below the default RTC queue_threshold (30) so the
# low-watermark always calls for a refill and inference latency is the sole throttle
# on the queue — which is what makes CG-4A-07f's exhaustion track the injected delay.
FIXTURE_CHUNK_LEN = 8


def make_dummy_robot(robot_id: str = "wp4a07-dummy") -> DummyOpenArmRobot:
    """Build and connect a committed dummy follower (no CAN, real observation schema).

    Args:
        robot_id: The instance id.

    Returns:
        (DummyOpenArmRobot) A connected dummy follower.
    """
    robot = DummyOpenArmRobot(DummyRobotConfig(id=robot_id))
    robot.connect()
    return robot


class ConnectCountingRobot(DummyOpenArmRobot):
    """A dummy that counts `connect()`/`disconnect()` so the switch invariant is measurable.

    The session must never reconnect on a backend switch (a reconnect re-zeros the arm,
    `FR-OPS-065/083`). This subclass makes that a counted fact: after the caller's one
    legitimate `connect()`, the count must stay at 1 across every switch (CG-4A-07e).
    """

    def __init__(self, config: DummyRobotConfig) -> None:
        """Construct the counting dummy with both counters at zero.

        Args:
            config: The dummy follower config.
        """
        super().__init__(config)
        self.connect_calls = 0
        self.disconnect_calls = 0

    def connect(self, calibrate: bool = True) -> None:
        """Count and delegate to the dummy connect.

        Args:
            calibrate: Passed through to the base connect (a no-op for a dummy).
        """
        self.connect_calls += 1
        super().connect(calibrate)

    def disconnect(self) -> None:
        """Count and delegate to the dummy disconnect."""
        self.disconnect_calls += 1
        super().disconnect()


def make_counting_robot(robot_id: str = "wp4a07-count") -> ConnectCountingRobot:
    """Build a connected `ConnectCountingRobot`; the one legitimate connect is the caller's.

    Args:
        robot_id: The instance id.

    Returns:
        (ConnectCountingRobot) A connected counting follower (`connect_calls == 1`).
    """
    robot = ConnectCountingRobot(DummyRobotConfig(id=robot_id))
    robot.connect()
    return robot


class FixturePolicy:
    """A deterministic, torch-free `ChunkPolicy` stand-in for a trained checkpoint.

    Emits reproducible 16-wide position vectors so the gates assert on a known stream.
    `reset_calls` records episode/switch resets so a test can prove state was cleared
    (`FR-INF-066`). `relative_action` selects whether the policy is relative — the flag
    the sync/RTC gate reads (CG-4A-07d).
    """

    def __init__(self, relative_action: bool = False, chunk_len: int = FIXTURE_CHUNK_LEN) -> None:
        """Build the fixture policy.

        Args:
            relative_action: Whether the policy emits relative actions (gates `sync`).
            chunk_len: Actions returned by `predict_action_chunk`.
        """
        self._profile = PolicyProfile(policy_type="act", relative_action=relative_action)
        self._chunk_len = chunk_len
        self.reset_calls = 0
        self._step = 0

    def reset(self) -> None:
        """Clear episode-scoped state and count the reset."""
        self.reset_calls += 1
        self._step = 0

    def select_action(self, observation: object) -> Sequence[float]:
        """Return one deterministic 16-wide action.

        Args:
            observation: The observation frame (unused by the fixture).

        Returns:
            (Sequence[float]) A `BIMANUAL_ACTION_DIM`-wide vector.
        """
        self._step += 1
        return self._vector(self._step)

    def predict_action_chunk(self, observation: object) -> Sequence[Sequence[float]]:
        """Return a deterministic chunk of `chunk_len` 16-wide actions.

        Args:
            observation: The observation frame (unused by the fixture).

        Returns:
            (Sequence[Sequence[float]]) `chunk_len` vectors, each 16-wide.
        """
        base = self._step
        self._step += self._chunk_len
        return [self._vector(base + index) for index in range(1, self._chunk_len + 1)]

    @property
    def profile(self) -> PolicyProfile:
        """The static profile the factory reads to gate a backend selection."""
        return self._profile

    def _vector(self, seed: int) -> list[float]:
        """Build a reproducible 16-wide vector from a seed.

        Args:
            seed: The step-derived seed.

        Returns:
            (list[float]) A `BIMANUAL_ACTION_DIM`-wide vector.
        """
        return [float((seed + joint) % 10) for joint in range(BIMANUAL_ACTION_DIM)]


def make_lineage() -> LineageRecord:
    """Build a minimal but complete WP-4A-05 lineage record (its `validate()` passes).

    Every one of the eight `FR-TRN-054` elements is present, so this is a checkpoint the
    factory will serve; the incomplete-lineage tests mutate a copy to drop an element.

    Returns:
        (LineageRecord) A complete lineage record.
    """
    return LineageRecord(
        dataset=DatasetLineage(
            repo_id="openarm/pick_place",
            revision="rev1",
            info_hash="info-hash",
            stats_hash="stats-hash",
        ),
        observation=ObservationConfig(
            use_velocity_and_torque=True,
            state_shape=1,
            action_shape=BIMANUAL_ACTION_DIM,
            names=("left_joint1.pos",),
        ),
        merge_history=(MergeHistoryEntry(source_session="sess-1", episode_index_map={0: 0}),),
        train_config={"policy": {"type": "act"}},
        pins=VersionPins(
            code_sha="0" * 40,
            lerobot_version="0.6.0",
            container_digest=CONTAINER_NOT_USED,
        ),
        degenerate_decisions=(),
    )
