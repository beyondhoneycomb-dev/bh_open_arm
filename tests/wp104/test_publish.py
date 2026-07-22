"""Acceptance ①⑤-b⑥⑦⑩⑪ and the publication-refusal guards ②③④.

The artifact carries the seven conditions and their full histograms (from the reused
synthetic run), the provisional verdicts and f_max, the comparison table and the
re-derivation trigger; and it is refused whenever the session lost its lock, ran
torque-on, or connected the wrong number of times.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.can.lock.manager import LockManager
from backend.rtbench.constants import REQUIRED_STALE_TRIGGER
from backend.rtbench.publish import (
    MeasurementArtifactRefusedError,
    _assert_provisional_marked,
    build_measurement_artifact,
)
from backend.rtbench.session import ReadOnlyMeasurementSession, TorqueState
from sim.harness.harness import HarnessResult

_IFACES = ("oa_fl", "oa_fr")
_MOTOR_IDS = tuple(range(16))


def _all_off() -> TorqueState:
    return TorqueState(enabled=dict.fromkeys(_MOTOR_IDS, False))


class _FlippableTorque:
    """A torque probe that starts all-OFF and can be switched to engaged mid-session."""

    def __init__(self) -> None:
        self.engaged = False

    def __call__(self) -> TorqueState:
        state = dict.fromkeys(_MOTOR_IDS, False)
        if self.engaged:
            state[7] = True
        return TorqueState(enabled=state)


def _connected_session(manager: LockManager, probe=_all_off) -> ReadOnlyMeasurementSession[str]:
    session: ReadOnlyMeasurementSession[str] = ReadOnlyMeasurementSession(
        manager, _IFACES, lambda: "bound", probe
    )
    session.connect()
    return session


def test_happy_path_artifact_carries_conditions_verdicts_and_trigger(
    tmp_path: Path, harness_result: HarnessResult
) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    try:
        session = _connected_session(manager)
        artifact = build_measurement_artifact(
            session=session,
            harness_result=harness_result,
            host_id="dev-x86",
            is_fleet_target=False,
        )
    finally:
        manager.release_all()

    # ⑤-b: the provisional re-derivation trigger is declared.
    assert artifact["stale_on"] == [REQUIRED_STALE_TRIGGER]
    # ②: exactly one connect recorded.
    assert artifact["session"]["connect_call_count"] == 1
    # ①⑪: all seven conditions with their full distributions came through.
    conditions = artifact["synthetic_run"]["conditions"]
    assert [c["number"] for c in conditions] == [1, 2, 3, 4, 5, 6, 7]
    assert artifact["synthetic_run"]["conditions"][0]["distribution"]["raw_samples"]
    # ⑤: the PG-RT-001a verdict is present and provisional.
    assert artifact["pg_rt_001a"]["gate"] == "PG-RT-001a"
    assert artifact["pg_rt_001a"]["provisional"] is True
    # ⑧: the frame verdict starts from the synthetic model, marked provisional.
    assert artifact["pg_can_001"][0]["source"] == "synthetic-model"
    assert artifact["pg_can_001"][0]["status"] == "PROVISIONAL"
    # ⑨: f_max is provisional and awaiting the deferred CAN bound.
    assert artifact["f_max"]["provisional"] is True
    assert "f_max_can" in artifact["f_max"]["awaiting"]
    # ⑥: the comparison table's real column is deferred.
    assert artifact["comparison_table"]["real"] is None
    assert artifact["comparison_table"]["synthetic"] is not None
    # ⑦: the GIL contribution and RT gain rode along in the synthetic run.
    assert "gil_contribution" in artifact["synthetic_run"]
    # ⑩: the x86 dev host is recorded as not-a-fleet-target.
    assert artifact["target_host"]["is_fleet_target"] is False
    # the real-CAN inputs are declared awaited, not invented.
    assert len(artifact["deferred"]["awaited_inputs"]) == 3


def test_real_candump_count_is_judged_alongside_the_model(
    tmp_path: Path, harness_result: HarnessResult
) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    try:
        session = _connected_session(manager)
        artifact = build_measurement_artifact(
            session=session,
            harness_result=harness_result,
            host_id="rig",
            is_fleet_target=True,
            real_frames_per_cycle=32,
        )
    finally:
        manager.release_all()
    verdicts = artifact["pg_can_001"]
    assert len(verdicts) == 2
    assert verdicts[1]["source"] == "real-candump"
    assert verdicts[1]["status"] == "PASS"


def test_publish_without_the_lock_is_refused(tmp_path: Path, harness_result: HarnessResult) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    session = _connected_session(manager)
    manager.release_all()  # lose the lock after connecting
    with pytest.raises(MeasurementArtifactRefusedError, match="lock"):
        build_measurement_artifact(
            session=session,
            harness_result=harness_result,
            host_id="dev-x86",
            is_fleet_target=False,
        )


def test_publish_with_torque_engaged_is_refused(
    tmp_path: Path, harness_result: HarnessResult
) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    try:
        probe = _FlippableTorque()
        session = _connected_session(manager, probe)
        probe.engaged = True  # a motor energises after connect
        with pytest.raises(MeasurementArtifactRefusedError, match="torque"):
            build_measurement_artifact(
                session=session,
                harness_result=harness_result,
                host_id="dev-x86",
                is_fleet_target=False,
            )
    finally:
        manager.release_all()


def test_publish_without_a_connected_session_is_refused(
    tmp_path: Path, harness_result: HarnessResult
) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    try:
        session: ReadOnlyMeasurementSession[str] = ReadOnlyMeasurementSession(
            manager, _IFACES, lambda: "bound", _all_off
        )
        with pytest.raises(MeasurementArtifactRefusedError):
            build_measurement_artifact(
                session=session,
                harness_result=harness_result,
                host_id="dev-x86",
                is_fleet_target=False,
            )
    finally:
        manager.release_all()


def test_provisional_guard_refuses_an_untriggered_artifact() -> None:
    # ⑤-b white-box: an artifact missing the re-derivation trigger is refused.
    with pytest.raises(MeasurementArtifactRefusedError, match="stale_on"):
        _assert_provisional_marked({"stale_on": []})
    _assert_provisional_marked({"stale_on": [REQUIRED_STALE_TRIGGER]})
