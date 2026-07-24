"""CG-4A-07b — remote `actions_per_chunk` missing refuses startup, and 50 is never prefilled.

Two halves. Runtime: `validate_remote_params(None)` refuses with a distinct reason and a
message that does not offer 50. Static: `find_actions_per_chunk_prefill` finds no `= 50`
prefill anywhere in the adapter tree, and — proving the scan actually bites (the
WP-BOOT-03 discipline) — flags a fixture snippet that does prefill 50. The upstream
`RobotClientConfig.actions_per_chunk` having no default is confirmed too, so the
required-argument contract our input stage front-runs is real.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from backend.inference.adapter import (
    InferenceParamError,
    InferenceParamReason,
    RemoteParams,
    advisory_max_roundtrip_sec,
    find_actions_per_chunk_prefill,
    scan_source,
    validate_remote_params,
)

ADAPTER_ROOT = Path("backend/inference/adapter")


def test_missing_actions_per_chunk_refuses_startup() -> None:
    """A missing `actions_per_chunk` (None) is refused with the missing reason."""
    with pytest.raises(InferenceParamError) as excinfo:
        validate_remote_params(RemoteParams(actions_per_chunk=None))
    assert excinfo.value.reason is InferenceParamReason.REMOTE_ACTIONS_PER_CHUNK_MISSING


def test_refusal_tells_operator_to_enter_the_value_not_prefill() -> None:
    """The refusal directs the operator to supply the value; nothing is prefilled.

    The message may (and does) warn that the official 50 is stale — that is the point —
    but the mechanism carries no default: `RemoteParams.actions_per_chunk` is None, so
    there is no value to prefill regardless of the wording.
    """
    with pytest.raises(InferenceParamError) as excinfo:
        validate_remote_params(RemoteParams(actions_per_chunk=None))
    message = str(excinfo.value).lower()
    assert "stale" in message
    assert "enter the value" in message
    assert RemoteParams().actions_per_chunk is None


def test_remote_params_default_is_not_fifty() -> None:
    """`RemoteParams.actions_per_chunk` defaults to None, never a prefilled 50."""
    field = {f.name: f for f in dataclasses.fields(RemoteParams)}["actions_per_chunk"]
    assert field.default is None


def test_no_fifty_prefill_in_adapter_tree() -> None:
    """The static scan finds no `actions_per_chunk = 50` prefill in the adapter source."""
    assert find_actions_per_chunk_prefill(ADAPTER_ROOT) == []


def test_static_scan_bites_on_a_prefill_fixture() -> None:
    """The scan flags every prefill form, proving it is not vacuously green."""
    offending = (
        "actions_per_chunk = 50\n"
        "def f(actions_per_chunk=50):\n"
        "    return actions_per_chunk\n"
        "build(actions_per_chunk=50)\n"
        "CONFIG = {'actions_per_chunk': 50}\n"
        "class C:\n"
        "    actions_per_chunk: int = 50\n"
    )
    violations = scan_source(offending, Path("fixture_prefill.py"))
    details = {violation.detail for violation in violations}
    assert details == {
        "assignment",
        "function default",
        "call keyword",
        "dict entry",
        "dataclass/field default",
    }


def test_upstream_robot_client_config_has_no_default() -> None:
    """LeRobot's `RobotClientConfig.actions_per_chunk` has no default — the contract is real."""
    from lerobot.async_inference.configs import RobotClientConfig

    field = {f.name: f for f in dataclasses.fields(RobotClientConfig)}["actions_per_chunk"]
    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING


def test_advisory_bound_computes_without_prefilling() -> None:
    """The NFR-INF-001 helper returns a bound to display, not a value to prefill.

    CG-4A-07b's negative branch: instead of prefilling, compute the round-trip bound the
    operator's own inputs imply. This is a pure function returning a number; it writes
    nothing back into any params object.
    """
    bound = advisory_max_roundtrip_sec(chunk_size_threshold=0.5, actions_per_chunk=50, fps=30)
    assert bound == pytest.approx((0.5 * 50) / 30)
    assert RemoteParams().actions_per_chunk is None
