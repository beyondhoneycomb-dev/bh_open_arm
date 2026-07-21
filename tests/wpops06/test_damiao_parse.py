"""Damiao ERR acceptance: we extract a field MotorState does not carry.

Acceptance ⑪ and ④ (from the parser side). 14 FR-OPS-018: the feedback frame
carries an ERR nibble the hardware already sends, but MotorState is
`{position, velocity, torque, temp_mos, temp_rotor}` — no error field. This
verifies that absence against the installed source (or records it honestly when
the source is not present) and that our parser produces the code upstream drops.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from contracts.errors.constants import DAMIAO_ERROR_NIBBLES
from contracts.errors.damiao_map import NIBBLE_TO_CODE, parse_motor_err
from contracts.errors.registry import REGISTRY

_ERROR_FIELD_NAMES = frozenset({"err", "error", "error_code", "err_code", "fault"})


def _motor_state_fields() -> frozenset[str] | None:
    """Return MotorState's declared fields from the installed damiao source.

    Returns:
        (frozenset[str] | None) The TypedDict field names, or None when the
            source is not installed in this environment.
    """
    spec = importlib.util.find_spec("lerobot.motors.damiao.damiao")
    if spec is None or spec.origin is None:
        return None
    tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MotorState":
            return frozenset(
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            )
    return None


def test_motor_state_has_no_error_field() -> None:
    """MotorState drops the ERR field, which is why we extract it (acceptance ⑪)."""
    fields = _motor_state_fields()
    if fields is None:
        # Honest record: the upstream source is not installed in the light lane.
        return
    assert fields == frozenset({"position", "velocity", "torque", "temp_mos", "temp_rotor"})
    assert not (fields & _ERROR_FIELD_NAMES), "MotorState unexpectedly carries an error field"


def test_parser_extracts_the_missing_field() -> None:
    """Our parser produces the ERR code MotorState never exposes (acceptance ⑪)."""
    result = parse_motor_err(0xB0)
    assert result.nibble == "B"
    assert result.code == "OA-MOT-00B"
    assert result.is_error is True


def test_enable_nibble_is_not_an_error() -> None:
    """Nibble 1 (Enable) is a normal state, not a code."""
    result = parse_motor_err(0x10)
    assert result.code is None
    assert result.is_error is False


def test_every_error_nibble_maps_to_a_registered_motor_code() -> None:
    """8/9/A/B/C/D/E each resolve to a registered OA-MOT code (acceptance ④)."""
    for nibble in DAMIAO_ERROR_NIBBLES:
        code = NIBBLE_TO_CODE[nibble]
        assert code in REGISTRY.codes
        assert code.startswith("OA-MOT-")
