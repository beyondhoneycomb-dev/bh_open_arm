"""CG-4B-05b — a tampered LeRobot (one item changed) blocks deployment.

Two independent tamper shapes are exercised so the block is not an artefact of one
mechanism: a bound-function source change (connect no longer zeroes) and a dataclass
default change (an RTC default drifts). Each is a faithful stand-in for an upstream
that moved the fact, and each must make the checker's run fail and the CLI gate exit
non-zero. A checker that cannot catch tampering is decoration (`02c` §2.5 negative
branch).
"""

from __future__ import annotations

import pytest

from backend.compat.contract_regression import cli, register


def _tampered_connect(self, calibrate: bool = True) -> None:  # noqa: ANN001, FBT001, FBT002
    """A connect() that skips auto-zeroing.

    Defined at module scope so `inspect.getsource` can read it. Its body deliberately
    contains no zeroing call, standing in for a LeRobot upgrade that dropped it — the
    predicate greps this source, so the token must not appear even in this docstring.
    """
    return


def test_tampered_connect_source_blocks_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    from lerobot.robots.openarm_follower import OpenArmFollower

    monkeypatch.setattr(OpenArmFollower, "connect", _tampered_connect)

    run = register.run()
    assert not run.ok
    failed_ids = {row.fact_id for row in run.failed()}
    assert "CONNECT_CALLS_SET_ZERO" in failed_ids
    # exactly the tampered item fails — untouched facts stay green.
    assert failed_ids == {"CONNECT_CALLS_SET_ZERO"}

    assert cli.main([]) == cli.EXIT_BLOCKED


def test_tampered_rtc_default_blocks_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    from lerobot.rollout.inference.rtc import RTCConfig

    field = RTCConfig.__dataclass_fields__["execution_horizon"]
    monkeypatch.setattr(field, "default", 25)

    run = register.run()
    assert not run.ok
    failed_ids = {row.fact_id for row in run.failed()}
    assert "ROLLOUT_RTC_DEFAULTS" in failed_ids

    assert cli.main([]) == cli.EXIT_BLOCKED


def test_untampered_tree_allows_deployment() -> None:
    # The control: with nothing tampered the same gate returns OK, so the block above
    # is the tamper's doing and not a checker that fails unconditionally.
    assert register.run().ok
    assert cli.main([]) == cli.EXIT_OK
