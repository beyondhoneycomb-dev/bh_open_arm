"""Acceptance ②: the jog step-delta cap and the velocity guard are separate paths.

The negative branch is concrete: a step-delta jump limit of 1.8 rad/step reused as a
velocity limit is 90 rad/s at 50 Hz — no limit at all. So the jog-path jump cap must
not be the velocity guard, and neither may stand in for the other. These are static
checks over the two modules' source: the jog cap reads `step_delta_limit_rad` and
never computes a velocity, and the velocity guard lives in the Wave-1 gateway filter
in a branch distinct from its own step-delta branch.
"""

from __future__ import annotations

import ast
import inspect

import pytest

import backend.actuation.safety as safety
import backend.jogclamp.path as jog_path
from backend.jogclamp import JogClampPath
from contracts.units import Deg


def _attributes_read(module: object) -> set[str]:
    """Every attribute name the module's *code* reads, docstrings and comments aside."""
    tree = ast.parse(inspect.getsource(module))
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def test_jog_step_cap_reads_step_delta_limit_not_velocity() -> None:
    """The jog code reads the jump limit field and never the velocity limit field."""
    attributes = _attributes_read(jog_path)
    assert "step_delta_limit_rad" in attributes
    assert "velocity_limit_rad_s" not in attributes


def test_jog_module_computes_no_velocity() -> None:
    """The jog code divides nothing, so it caps position deltas — it computes no rate."""
    tree = ast.parse(inspect.getsource(jog_path))
    # A velocity is a delta over a period: it requires a division. The jog cap has
    # none, so it cannot be a velocity limit wearing a step-cap name (acceptance ②).
    divisions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
    ]
    assert divisions == []
    assert "dt_sec" not in _attributes_read(jog_path)


def test_velocity_guard_and_step_delta_are_distinct_branches_in_the_gateway() -> None:
    """Wave-1's slew check keeps step-delta and velocity as separate limits/branches."""
    slew_source = inspect.getsource(safety.SafetyFilter._check_slew)
    assert "step_delta_limit_rad" in slew_source
    assert "velocity_limit_rad_s" in slew_source
    # The two guards raise distinct reasons, which is what "separate path" means here.
    assert "STEP_DELTA" in slew_source
    assert "VELOCITY_LIMIT" in slew_source


def test_jog_cap_does_not_bound_velocity(seeded_path: JogClampPath) -> None:
    """A jump within the jog cap is admitted regardless of how fast it implies moving.

    The point of keeping the two guards separate: the jog cap smooths a per-step jump
    but says nothing about rad/s, so a cap sized for smoothness would still let a
    velocity-abusive command through — which is exactly why the gateway velocity check
    remains a separate, mandatory backstop, not something this path replaces.
    """
    # Joint 1's jump cap is 0.2 rad ≈ 11.459°. A step right at the cap is admitted
    # unaltered; the jog path renders no verdict on the implied rad/s at any dt.
    result = seeded_path.apply((Deg(0.0), Deg(11.4591559), Deg(0.0)))
    assert result.accepted_deg[1].value == pytest.approx(11.4591559)
    assert not result.clamped
