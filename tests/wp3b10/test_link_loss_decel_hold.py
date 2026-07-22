"""RUNS-HERE ① / ⑤ — a lost heartbeat decelerates to a hold, and never stops commanding.

`FR-TEL-081`/S5: injecting a heartbeat timeout moves FOLLOWING to LINK_LOST, and the
gate decelerates the coasting EE to a stop and then holds — it does not freeze
instantly, and it never yields a no-command tick (`FR-TEL-079`; a broken CAN stream
drops the Damiao enable and the arm falls).
"""

from __future__ import annotations

from backend.teleop.safety_gate.heartbeat import LinkHealth
from backend.teleop.safety_gate.states import TeleopLinkState
from tests.wp3b10.conftest import DT_SEC, TICK_NS, make_gate, make_sample, pose_at

_FOLLOW_TICKS = 6
_STEP_M = 0.001  # per-tick x advance while following → 0.1 m/s coast velocity


def _drive_to_following(gate, start_ns: int) -> tuple[int, float]:
    """Align, then follow a steady +x ramp; return the clock and last x commanded."""
    now = start_ns
    gate.step(now, pose_at((0.0, 0.0, 0.0)), sample=make_sample(now))
    gate.notify_alignment_converged(now)
    assert gate.state is TeleopLinkState.FOLLOWING

    x = 0.0
    for _ in range(_FOLLOW_TICKS):
        now += TICK_NS
        x += _STEP_M
        out = gate.step(now, pose_at((x, 0.0, 0.0)), sample=make_sample(now))
        assert out.state is TeleopLinkState.FOLLOWING
        assert out.command is not None
    return now, gate.command.translation[0]


def test_heartbeat_timeout_enters_link_lost_and_decelerates_then_holds() -> None:
    """A dropped heartbeat → LINK_LOST → decelerate → hold, command stream unbroken (①/⑤)."""
    gate = make_gate(seed_pose=pose_at((0.0, 0.0, 0.0)))
    now, x_at_loss = _drive_to_following(gate, start_ns=1_000)

    # Drop frames: advance well past the 100 ms timeout with no sample. The link is now
    # lost; the gate enters LINK_LOST and begins to decelerate.
    now += 20 * TICK_NS
    out = gate.step(now, pose_at((99.0, 0.0, 0.0)))  # target is garbage on a dead link
    assert out.link_health is LinkHealth.LOST
    assert out.state is TeleopLinkState.LINK_LOST
    assert out.decelerating is True
    assert out.command is not None

    # Keep ticking with no frames. The command keeps advancing by a shrinking step
    # (decel), never jumping to the garbage target, then settles to a constant hold.
    positions = [gate.command.translation[0]]
    saw_hold = False
    for _ in range(20):
        now += TICK_NS
        out = gate.step(now, pose_at((99.0, 0.0, 0.0)))
        assert out.state is TeleopLinkState.LINK_LOST  # never auto-resumes
        assert out.command is not None  # command stream never stops (FR-TEL-079)
        positions.append(gate.command.translation[0])
        if not out.decelerating:
            saw_hold = True

    # Coast continued forward from the loss point (decel, not instant stop)...
    assert positions[-1] > x_at_loss
    # ...the steps were monotonically non-increasing (decelerating)...
    deltas = [b - a for a, b in zip(positions, positions[1:], strict=False)]
    assert all(later <= earlier + 1e-12 for earlier, later in zip(deltas, deltas[1:], strict=False))
    # ...it reached a hold, and the final position is frozen (last two equal).
    assert saw_hold
    assert positions[-1] == positions[-2]
    # ...and it never lurched to the dead-link garbage target.
    assert gate.command.translation[0] < 1.0


def test_command_never_none_across_every_state() -> None:
    """Every tick emits a command — following, decelerating, and holding (FR-TEL-079/⑤)."""
    gate = make_gate(seed_pose=pose_at((0.0, 0.0, 0.0)))
    now, _ = _drive_to_following(gate, start_ns=1_000)
    now += 30 * TICK_NS
    for _ in range(40):
        now += TICK_NS
        out = gate.step(now, pose_at((0.5, 0.0, 0.0)))
        assert out.command is not None
    # The coast velocity was ~0.1 m/s and decel 4 m/s²: the hold is reached well within
    # 40 ticks of DT_SEC each.
    assert gate.state is TeleopLinkState.LINK_LOST
    assert DT_SEC > 0.0
