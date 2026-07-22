"""The rig seam binds the session to the WP-1-03 follower's read path (offline stub).

The real follower needs the LeRobot stack and a CAN bus, so here a stub with the same
read-path surface — `connect_readonly` and `is_torque_enabled` — stands in, proving the
binding calls the read path and maps the enable state to the torque assertion. The real
follower on the rig is the deferred part.
"""

from __future__ import annotations

from backend.rtbench.rig import RigReadonlyConnect, RigTorqueProbe


class _StubFollower:
    """A follower stub exposing only the read-path surface the rig seam uses."""

    def __init__(self, torque_enabled: bool = False) -> None:
        self.is_torque_enabled = torque_enabled
        self.connect_readonly_calls = 0
        self.last_lock_manager: object | None = None

    def connect_readonly(self, lock_manager: object | None = None) -> None:
        self.connect_readonly_calls += 1
        self.last_lock_manager = lock_manager


def test_rig_connect_runs_connect_readonly_and_returns_the_follower() -> None:
    follower = _StubFollower()
    manager = object()
    connect = RigReadonlyConnect(follower, manager)  # type: ignore[arg-type]
    bound = connect()
    assert bound is follower
    assert follower.connect_readonly_calls == 1
    assert follower.last_lock_manager is manager


def test_rig_torque_probe_reflects_the_follower_enable_state() -> None:
    off = RigTorqueProbe(_StubFollower(torque_enabled=False))  # type: ignore[arg-type]
    assert off().all_off()
    on = RigTorqueProbe(_StubFollower(torque_enabled=True))  # type: ignore[arg-type]
    assert not on().all_off()
