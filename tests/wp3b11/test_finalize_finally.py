"""Acceptance ③/④: `finalize()` runs in a `finally` on every exit path.

A missing parquet footer invalidates the whole dataset (`02b` §6.2 WP-3B-11), so
`finalize()` must run whether the session returns normally, raises an exception
mid-loop, or is interrupted. Each path is injected here: a normal run, a robot
that raises `RuntimeError`, and a robot that raises `KeyboardInterrupt`. In all
three the fake dataset records that `finalize()` was called, and in the two
failing paths the original error still propagates.

The dataset is faked so the assertion is on the control flow alone; a real
end-to-end finalize is exercised by the re-record and reset tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import backend.recorder.embed.session as session_mod
from backend.recorder.embed import RecordEvents, RecordSpec, record_session

from ._support import DummyRobotAdapter, ExplodingRobot, FakeDataset, RampTeleop

FPS = 30


def _spec() -> RecordSpec:
    """A one-episode session spec sized for a fast injection test."""
    return RecordSpec(
        repo_id="synthetic/finalize",
        single_task="grab",
        fps=FPS,
        bimanual=True,
        use_velocity_and_torque=True,
        num_episodes=1,
        episode_steps=4,
        reset_steps=2,
    )


def _install_fake_dataset(monkeypatch: pytest.MonkeyPatch) -> FakeDataset:
    """Make `record_session` create a fake dataset, and return it for inspection."""
    fake = FakeDataset(fps=FPS)
    monkeypatch.setattr(
        session_mod,
        "create_record_dataset",
        lambda *_args, **_kwargs: (fake, "synthetic/finalize_stamped"),
    )
    return fake


def test_finalize_runs_on_normal_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A session that completes normally finalizes exactly once."""
    fake = _install_fake_dataset(monkeypatch)
    events = RecordEvents()
    record_session(_spec(), DummyRobotAdapter(True, True), RampTeleop(True), events, tmp_path)
    assert fake.finalize_calls == 1
    assert fake.save_calls == 1


def test_finalize_runs_when_the_loop_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An exception raised inside the loop still passes through finalize, then propagates."""
    fake = _install_fake_dataset(monkeypatch)
    robot = ExplodingRobot(
        DummyRobotAdapter(True, True), fail_on_call=2, error=RuntimeError("boom")
    )
    with pytest.raises(RuntimeError, match="boom"):
        record_session(_spec(), robot, RampTeleop(True), RecordEvents(), tmp_path)
    assert fake.finalize_calls == 1
    assert fake.save_calls == 0


def test_finalize_runs_on_interruption(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A KeyboardInterrupt mid-loop still runs finalize, then propagates."""
    fake = _install_fake_dataset(monkeypatch)
    robot = ExplodingRobot(DummyRobotAdapter(True, True), fail_on_call=2, error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        record_session(_spec(), robot, RampTeleop(True), RecordEvents(), tmp_path)
    assert fake.finalize_calls == 1


def test_finalize_precedes_no_skippable_teardown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """finalize is the first thing in the finally: a later teardown cannot skip it.

    The failing loop leaves the fake with a non-empty buffer; finalize must still be
    the call that ran, proving nothing between the raise and finalize was allowed to
    swallow the footer write.
    """
    fake = _install_fake_dataset(monkeypatch)
    robot = ExplodingRobot(DummyRobotAdapter(True, True), fail_on_call=3, error=RuntimeError("x"))
    with pytest.raises(RuntimeError):
        record_session(_spec(), robot, RampTeleop(True), RecordEvents(), tmp_path)
    assert fake.finalize_calls == 1
