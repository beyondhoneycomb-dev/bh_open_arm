"""Acceptance ② — dummy↔real swap changes 0 caller lines.

A caller written against the `OpenArmRobot`/`Robot` ABC must drive the dummy and a
real backend with no changed line. This is shown three ways:

- The dummy inherits the frozen feature contract unchanged — it does not redeclare
  `observation_features` / `action_features` — so any two `OpenArmRobot` subclasses
  present one schema. `_ReferenceBackend` stands in for a real backend at the
  interface (WP-1 owns the real one); the same caller runs against it and the dummy
  and returns identical interface results.
- The dummy is a concrete `Robot`: no abstract method is left unimplemented, so it
  substitutes wherever a `Robot` is expected.
- The caller's own source names no dummy-specific symbol, so swapping the concrete
  class cannot force a caller edit.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from lerobot.robots.robot import Robot, RobotAction, RobotObservation

from contracts.plugin.robot_abc import OpenArmRobot
from packages.lerobot_robot_openarm_dummy import (
    REAL_OBSERVATION_FEATURES,
    DummyOpenArmRobot,
    DummyRobotConfig,
)


class _ReferenceBackend(OpenArmRobot):
    """A minimal `OpenArmRobot` standing in for a real backend at the interface.

    It inherits the same frozen feature contract the dummy does and returns a
    schema-valid frame, so it is exactly what a caller would swap the dummy for.
    """

    name = "reference_backend"
    config_class = DummyRobotConfig

    def __init__(self, config: DummyRobotConfig) -> None:
        super().__init__(config)
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_calibrated(self) -> bool:
        return True

    def connect(self, calibrate: bool = True) -> None:
        self._connected = True
        if calibrate and not self.is_calibrated:
            self.calibrate()

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    def get_observation(self) -> RobotObservation:
        return {
            name: (0 if declared is int else 0.0)
            for name, declared in REAL_OBSERVATION_FEATURES.items()
        }

    def send_action(self, action: RobotAction) -> RobotAction:
        return dict(action)

    def disconnect(self) -> None:
        self._connected = False


def run_interface_cycle(robot: OpenArmRobot) -> tuple[frozenset[str], frozenset[str]]:
    """Drive one interface cycle against any OpenArm backend.

    This is the caller under test: it depends only on the ABC surface — connect,
    the feature dicts, get_observation, send_action, disconnect — and names no
    concrete backend. It is what a record/teleop loop compiles down to.

    Args:
        robot: Any OpenArm backend.

    Returns:
        (tuple[frozenset[str], frozenset[str]]) The observation and action field sets
        seen through the interface.
    """
    robot.connect()
    observation = robot.get_observation()
    action = dict.fromkeys(robot.action_features, 0.0)
    applied = robot.send_action(action)
    robot.disconnect()
    return frozenset(observation), frozenset(applied)


def test_dummy_does_not_redeclare_the_frozen_schema() -> None:
    """The dummy inherits, never overrides, the frozen feature contract."""
    assert DummyOpenArmRobot.observation_features is OpenArmRobot.observation_features
    assert DummyOpenArmRobot.action_features is OpenArmRobot.action_features


def test_dummy_is_a_concrete_robot() -> None:
    """No abstract method is left unimplemented, so the dummy substitutes for a Robot."""
    assert issubclass(DummyOpenArmRobot, Robot)
    assert issubclass(DummyOpenArmRobot, OpenArmRobot)
    assert DummyOpenArmRobot.__abstractmethods__ == frozenset()


def test_same_caller_runs_against_dummy_and_reference(tmp_path: Path) -> None:
    """One caller, two backends, identical interface field sets — a zero-line swap."""
    dummy = DummyOpenArmRobot(DummyRobotConfig(id="dummy", calibration_dir=tmp_path))
    reference = _ReferenceBackend(DummyRobotConfig(id="real", calibration_dir=tmp_path))

    dummy_fields = run_interface_cycle(dummy)
    reference_fields = run_interface_cycle(reference)

    assert dummy_fields == reference_fields
    assert dummy_fields[0] == frozenset(REAL_OBSERVATION_FEATURES)


def test_caller_names_no_dummy_symbol() -> None:
    """The caller references no dummy-specific name, so the swap cannot touch it."""
    source = inspect.getsource(run_interface_cycle).lower()
    assert "dummy" not in source
    assert "reference_backend" not in source
