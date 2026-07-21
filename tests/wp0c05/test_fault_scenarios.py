"""Acceptance ④ — at least six fault scenarios, each provoking its upstream reaction.

The library must carry the six named faults — obs-missing, packet-drop, stale,
bus-off (simulated), partial-connect, response-lag — and each must drive the *real*
upstream that reacts to it: the schema validator, the drop monitor, the actuation
scheduler, the connect contract, and the deadline monitor. A fault-free control of
each checker must NOT react, so a green scenario proves the fault caused the
reaction rather than the checker always firing.
"""

from __future__ import annotations

from pathlib import Path

from backend.actuation.emissions import EmissionLabel
from backend.actuation.harness import FaultInjectionHarness
from packages.lerobot_robot_openarm_dummy import (
    DropMonitor,
    DummyOpenArmRobot,
    DummyRobotConfig,
    FaultKind,
    ObservationDeadlineMonitor,
    Reaction,
    observation_field_diff,
    scenario_library,
)
from packages.lerobot_robot_openarm_dummy.injection import OBSERVATION_DEADLINE_SEC

_REQUIRED_KINDS = frozenset(FaultKind)


def test_library_has_at_least_six_distinct_faults() -> None:
    """The six named fault kinds are all present, each once."""
    kinds = [scenario.kind for scenario in scenario_library()]
    assert len(kinds) >= 6
    assert set(kinds) == _REQUIRED_KINDS
    assert len(kinds) == len(set(kinds))


def test_each_scenario_triggers_its_upstream_reaction(tmp_path: Path) -> None:
    """Every scenario's runner produces exactly its declared upstream reaction."""
    for scenario in scenario_library():
        observed = scenario.run(tmp_path)
        assert observed is scenario.expected, (
            f"{scenario.kind.value}: {observed} != {scenario.expected}"
        )
        assert observed is not Reaction.NONE


def test_healthy_schema_check_does_not_react(tmp_path: Path) -> None:
    """A well-formed frame is not schema-rejected — obs-missing bites only on a fault."""
    robot = DummyOpenArmRobot(DummyRobotConfig(id="f", calibration_dir=tmp_path))
    robot.connect()
    missing, extra = observation_field_diff(robot.get_observation())
    assert missing == frozenset()
    assert extra == frozenset()


def test_healthy_drop_monitor_does_not_react(tmp_path: Path) -> None:
    """Two healthy frames do not flag a drop — the packet-drop check is not perpetual."""
    robot = DummyOpenArmRobot(DummyRobotConfig(id="f", calibration_dir=tmp_path))
    robot.connect()
    monitor = DropMonitor()
    monitor.flagged(robot.get_observation())
    assert monitor.flagged(robot.get_observation()) is False


def test_healthy_deadline_monitor_does_not_react() -> None:
    """A prompt observation does not overrun — the response-lag check is not perpetual."""
    monitor = ObservationDeadlineMonitor(OBSERVATION_DEADLINE_SEC)
    assert monitor.overrun(0.0) is False


def test_fresh_source_holds_no_stale(tmp_path: Path) -> None:
    """A continuously fresh source yields ACCEPTED, not a stale-source hold."""
    harness = FaultInjectionHarness()
    emission = harness.run_tick(publish=True, renew=True)
    assert emission.label is EmissionLabel.ACCEPTED_TARGET


def test_full_connect_is_not_refused(tmp_path: Path) -> None:
    """A follower with no failed channels connects — partial-connect refuses only on a fault."""
    robot = DummyOpenArmRobot(DummyRobotConfig(id="f", calibration_dir=tmp_path))
    robot.connect()
    assert robot.is_connected
