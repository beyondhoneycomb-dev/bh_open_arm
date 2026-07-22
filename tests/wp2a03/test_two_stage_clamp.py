"""The two-stage clamp application: mechanical then operational, each attributable.

`clamp_stage1` clips to the mechanical URDF envelope, `clamp_stage2` to the tighter
operational envelope. Operational is a subset of mechanical, so stage 2 dominates the
final value; the separate stages exist so a request that escaped the mechanical
envelope (a producer fault) stays a distinct, counted event from one merely outside
the operational envelope (a normal operating clamp).
"""

from __future__ import annotations

from backend.jogclamp import JogClampPath, JogClampReason
from contracts.units import Deg


def test_stage1_clips_to_mechanical(seeded_path: JogClampPath) -> None:
    """Stage 1 alone clips a target to the mechanical envelope."""
    clipped, hit = seeded_path.clamp_stage1((Deg(250.0), Deg(0.0), Deg(0.0)))
    assert hit
    assert clipped[0].value == 180.0


def test_stage2_clips_to_operational(seeded_path: JogClampPath) -> None:
    """Stage 2 alone clips a target to the tighter operational envelope."""
    # 120° is inside joint 0's mechanical [-180, 180] but outside its operational
    # [-90, 90], so the operational stage clips it while the mechanical stage would not.
    clipped, hit = seeded_path.clamp_stage2((Deg(120.0), Deg(0.0), Deg(0.0)))
    assert hit
    assert clipped[0].value == 90.0


def test_request_beyond_mechanical_fires_both_stages(seeded_path: JogClampPath) -> None:
    """A raw request outside the mechanical envelope counts a mechanical AND operational clamp."""
    result = seeded_path.apply((Deg(250.0), Deg(0.0), Deg(0.0)))
    assert JogClampReason.MECHANICAL_LIMIT in result.reasons
    assert JogClampReason.OPERATIONAL_LIMIT in result.reasons
    # Mechanical is the first reason: it fires before operational in the pipeline.
    assert result.reasons[0] is JogClampReason.MECHANICAL_LIMIT


def test_request_inside_mechanical_fires_only_operational(seeded_path: JogClampPath) -> None:
    """A request within mechanical but outside operational is only an operational clamp."""
    result = seeded_path.apply((Deg(120.0), Deg(0.0), Deg(0.0)))
    assert JogClampReason.MECHANICAL_LIMIT not in result.reasons
    assert JogClampReason.OPERATIONAL_LIMIT in result.reasons


def test_final_value_is_bounded_by_operational_when_both_fire(seeded_path: JogClampPath) -> None:
    """Even when the mechanical stage fires, the emitted value respects operational."""
    # Seed joint 0 near the operational edge so the jump cap does not mask the result.
    seeded_path.seed_previous((Deg(89.0), Deg(0.0), Deg(0.0)))
    result = seeded_path.apply((Deg(250.0), Deg(0.0), Deg(0.0)))
    # Operational high is 90°; the emitted value never exceeds it despite the request
    # being outside even the mechanical envelope.
    assert result.accepted_deg[0].value <= 90.0
