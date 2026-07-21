"""The victim control loop whose cycle time the harness measures.

The loop stands in for the LeRobot control loop `PG-RT-001` measures: it runs at a
target frequency and, each tick, does a representative control-tick's worth of Python
work, then waits the remainder of the period (LeRobot's `busy_wait(1/fps - dt)`
shape). The measured quantity is the wall time between consecutive iteration starts —
the cycle time that inflates when a GIL-holding load thread is scheduled while the
loop is trying to wake.

The three no-load conditions differ only in the per-tick payload:

  * idle (condition 1): build the full observation frame + echo the action — the
    shape of one `get_observation()` + `send_action()`.
  * pattern A (condition 2): the lighter 16-frame/cycle path that skips the full
    observation read and uses the MIT response as state (`15` §2.1).
  * full teleop (condition 3): idle plus a synthetic `teleop.get_action()` — a
    UDP-style packet decode, a One-Euro filter, and a small IK solve.

The dummy (`WP-0C-05`) is the bench device this loop is bound to, but it is never
connected: `connect()` is called zero times (acceptance, `02a` WP-0C-06), because
binding to a real rig and its single session `connect()` is `WP-1-04`'s job. The
payload builds frames from the frozen observation/action channel names the dummy
would return, which is how the dummy is consumed without opening a session.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum

import numpy as np

# Per-channel synthetic scalar work: a couple of float ops so building a frame is not
# elided to a bare dict literal, matching the order of real per-channel unpacking.
_CHANNEL_BASE_DEG = 0.01

# One-Euro filter smoothing factor for the synthetic teleop stage — a representative
# constant, not tuned against any rig (the teleop path here only models CPU shape).
_ONE_EURO_ALPHA = 0.3

# The synthetic IK solve is a small dense system per arm joint group; 7 is the
# per-arm DoF the real IK adapter (`WP-0C-02`) solves for.
_IK_DIMENSION = 7

# A UDP teleop packet on the wire is a few dozen float64s (pose + buttons); this many
# models the decode/copy cost without a real socket.
_TELEOP_PACKET_FLOATS = 32

Payload = Callable[[], None]


class PayloadKind(Enum):
    """Which control-tick payload the victim loop runs (conditions 1-3)."""

    IDLE = "idle"
    PATTERN_A = "pattern_a"
    TELEOP = "teleop"


class DummyBinding:
    """The bench binding to the `WP-0C-05` dummy — held, never connected.

    Ownership: constructs and holds one `DummyOpenArmRobot` and the frozen channel
    names it would report. It exposes `connect_call_count`, which stays 0 for the
    harness's whole life because the offline harness never opens a rig session
    (real-rig binding is `WP-1-04`). The lerobot/contract imports are deferred to
    construction so the timing and statistics core stay importable without the robot
    stack.
    """

    def __init__(self) -> None:
        """Bind the dummy and read its channel names without connecting it."""
        from contracts.plugin.robot_abc import (
            openarm_action_features,
            openarm_observation_features,
        )
        from packages.lerobot_robot_openarm_dummy.config import DummyRobotConfig
        from packages.lerobot_robot_openarm_dummy.robot import DummyOpenArmRobot

        self._robot = DummyOpenArmRobot(DummyRobotConfig())
        self._observation_channels = tuple(openarm_observation_features(bimanual=True).keys())
        self._action_channels = tuple(openarm_action_features(bimanual=True).keys())
        self._connect_call_count = 0

    @property
    def observation_channels(self) -> tuple[str, ...]:
        """The observation channel names the bound device reports."""
        return self._observation_channels

    @property
    def action_channels(self) -> tuple[str, ...]:
        """The position-action channel names the bound device accepts."""
        return self._action_channels

    @property
    def connect_call_count(self) -> int:
        """How many times the harness connected the dummy — always 0 for `WP-0C-06`."""
        return self._connect_call_count

    def connect_readonly(self) -> None:
        """Open a session on the bound device — deliberately unused by this harness.

        Present so the count is a real instrument rather than a hardcoded zero: were
        the harness ever to open a session, this is the single path it would take, and
        the counter would move. `WP-1-04` is where that binding actually happens.
        """
        self._connect_call_count += 1
        self._robot.connect(calibrate=False)


class _IdlePayload:
    """Build a full observation frame and echo the action — one idle control tick."""

    def __init__(self, binding: DummyBinding) -> None:
        """Capture the channel names the tick builds frames over."""
        self._observation_channels = binding.observation_channels
        self._action_channels = binding.action_channels
        self._step = 0

    def __call__(self) -> None:
        """Run one idle tick's representative work."""
        self._step += 1
        base = self._step * _CHANNEL_BASE_DEG
        observation = {
            name: base + len(name) * _CHANNEL_BASE_DEG for name in self._observation_channels
        }
        action = {name: observation.get(name, base) for name in self._action_channels}
        # Touch the built structures so the work is not optimised away.
        _ = len(observation) + len(action)


class _PatternAPayload:
    """The lighter pattern-A tick: no full observation read, MIT response as state."""

    def __init__(self, binding: DummyBinding) -> None:
        """Capture the action channel names the pattern-A path works over."""
        self._action_channels = binding.action_channels
        self._step = 0

    def __call__(self) -> None:
        """Run one pattern-A tick — only the action-sized state is touched."""
        self._step += 1
        base = self._step * _CHANNEL_BASE_DEG
        state = {name: base + len(name) * _CHANNEL_BASE_DEG for name in self._action_channels}
        _ = len(state)


class _TeleopPayload:
    """Idle work plus a synthetic teleop input: packet decode, One-Euro, IK solve."""

    def __init__(self, binding: DummyBinding) -> None:
        """Prepare the idle sub-tick and the fixed-size IK system."""
        self._idle = _IdlePayload(binding)
        self._action_dim = len(binding.action_channels)
        self._filtered = np.zeros(self._action_dim, dtype=np.float64)
        self._ik_matrix = np.eye(_IK_DIMENSION, dtype=np.float64) + 0.1
        self._ik_target = np.ones(_IK_DIMENSION, dtype=np.float64)

    def __call__(self) -> None:
        """Run one full-teleop tick: idle work then the teleop input pipeline."""
        self._idle()
        packet = np.frombuffer(
            np.linspace(0.0, 1.0, _TELEOP_PACKET_FLOATS, dtype=np.float64).tobytes(),
            dtype=np.float64,
        )
        raw = np.resize(packet, self._action_dim)
        self._filtered = _ONE_EURO_ALPHA * raw + (1.0 - _ONE_EURO_ALPHA) * self._filtered
        np.linalg.solve(self._ik_matrix, self._ik_target)


def make_payload(kind: PayloadKind, binding: DummyBinding) -> Payload:
    """Build the per-tick payload for a condition.

    Args:
        kind: Which payload the condition runs.
        binding: The dummy binding the payload builds frames from.

    Returns:
        (Payload) A zero-argument callable running one control tick's work.
    """
    if kind is PayloadKind.PATTERN_A:
        return _PatternAPayload(binding)
    if kind is PayloadKind.TELEOP:
        return _TeleopPayload(binding)
    return _IdlePayload(binding)


def run_control_loop(
    target_hz: float,
    tick_count: int,
    warmup: int,
    payload: Payload,
) -> np.ndarray:
    """Run the victim loop and return its cycle-time samples.

    The loop has LeRobot's shape: each iteration does the control work, then waits the
    remainder of the period measured from that iteration's *start* (a relative period,
    like `busy_wait(1/fps - dt)`). The cycle time is the interval between consecutive
    iteration starts, so a stall in one cycle — whether the work is delayed or the
    post-work sleep wakes late because a load thread holds the GIL — inflates that
    cycle rather than being silently absorbed by a self-correcting absolute deadline.
    That is what makes the loaded and idle cycle-time distributions distinguishable
    when the load bites (acceptance ③).

    The wait uses `time.sleep`, which releases the GIL: the load thread runs during
    the wait and, on wake, the victim must re-acquire the GIL — the exact point GIL
    contention delays it.

    Args:
        target_hz: Target loop frequency; the period is `1 / target_hz`.
        tick_count: How many measured cycles to collect (after warmup).
        warmup: Cycles to run and discard before measuring, so first-touch and
            scheduler settling do not bias the distribution.
        payload: The per-tick control work.

    Returns:
        (np.ndarray) `tick_count` cycle times in seconds — the interval between
        consecutive iteration starts.
    """
    period = 1.0 / target_hz
    perf_counter = time.perf_counter
    sleep = time.sleep

    total = warmup + tick_count
    starts = np.empty(total + 1, dtype=np.float64)
    for index in range(total + 1):
        start = perf_counter()
        starts[index] = start
        payload()
        remaining = period - (perf_counter() - start)
        if remaining > 0.0:
            sleep(remaining)
    cycles = np.diff(starts)
    return cycles[warmup:]


def measure_self_overhead(iterations: int) -> dict[str, float]:
    """Measure the instrument's own per-sample cost (acceptance ⑦).

    This runs the bare measurement bookkeeping — two `perf_counter` reads and a store,
    with no payload and no sleep — so a reader can tell how much of a measured cycle
    time is the harness observing itself versus real load. It is the harness's noise
    floor, recorded alongside the results rather than silently assumed to be zero.

    Args:
        iterations: How many bookkeeping samples to take.

    Returns:
        (dict[str, float]) `iterations`, and the `min`/`median`/`mean` per-sample
        overhead in seconds.
    """
    perf_counter = time.perf_counter
    samples = np.empty(iterations, dtype=np.float64)
    previous = perf_counter()
    for index in range(iterations):
        now = perf_counter()
        samples[index] = now - previous
        previous = now
    return {
        "iterations": float(iterations),
        "min": float(samples.min()),
        "median": float(np.median(samples)),
        "mean": float(samples.mean()),
    }
