"""WP-ENV-04 — upstream contract-regression predicates (import + introspect).

Every fact `16` §10.1/§10.2 and `01` §2.18 cite about the installed upstream
(LeRobot, openarm_control, python-can) is checked here by importing the package
and inspecting a real symbol — signature, dataclass default, or the bound
function's own source (`inspect.getsource`) — never by matching a file's text at a
line number. Line numbers in the citations address the upstream git tree; the
equivalent runtime symbol is what this module interrogates instead.

This module deliberately lives outside the plan-machine import path: `registry.
check` never imports it, so the light lane (pyyaml + jsonschema) keeps running
without the robot stack. The heavy imports sit inside each predicate so the
module itself is importable for name resolution even where the stack is absent.

`CHECKER_VERSION` is an input to `env_hash` (`registry.env.env_hash`): bump it
whenever a predicate's meaning changes so a downstream manifest pinned to the old
environment goes stale.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass

CHECKER_VERSION = "env04-upstream-facts@1"


@dataclass(frozen=True)
class FactResult:
    """The outcome of one upstream-fact predicate.

    Attributes:
        ok: True when the installed upstream still matches the cited fact.
        expected: What the fact asserts.
        actual: What introspection found.
    """

    ok: bool
    expected: str
    actual: str


def _dataclass_field_default(module_name: str, class_name: str, field_name: str) -> object:
    """Return a dataclass field's declared default (or its factory's product).

    Args:
        module_name: Dotted module to import.
        class_name: Dataclass attribute in that module.
        field_name: Field whose default is wanted.

    Returns:
        (object) The default value, `dataclasses.MISSING` when required, or a
            sentinel string when the field is absent.
    """
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    for field in dataclasses.fields(cls):
        if field.name != field_name:
            continue
        if field.default is not dataclasses.MISSING:
            declared: object = field.default
            return declared
        factory = field.default_factory
        if factory is not dataclasses.MISSING:
            produced: object = factory()
            return produced
        return dataclasses.MISSING
    return "<field-absent>"


def send_action_tau_dq_zero_hardcode() -> FactResult:
    """`12` §2.7.0 — `send_action` hardcodes the velocity and torque channels to 0.

    Acceptance ④: this must be true on the current pin; if it ever becomes false
    the `12` §2.7 premise collapses. The MIT command tuple is `(kp, kd, pos, dq,
    tau)`; the fact holds when the two trailing channels are literal `0.0`.
    """
    from lerobot.robots.openarm_follower import OpenArmFollower

    source = inspect.getsource(OpenArmFollower.send_action)
    hardcoded = bool(re.search(r",\s*0\.0\s*,\s*0\.0\s*\)", source))
    found = "dq/tau literal-0.0 tuple present" if hardcoded else "no (..., 0.0, 0.0) tuple found"
    return FactResult(
        ok=hardcoded,
        expected="send_action builds an MIT tuple ending in (..., 0.0, 0.0) — dq/tau pinned to 0",
        actual=found,
    )


def mit_control_batch_accepts_tau() -> FactResult:
    """`16` §10.1 — the bus-level torque channel is already open in `_mit_control_batch`.

    The batch command value is a 5-float tuple `(kp, kd, pos, dq, tau)`; the fifth
    slot is the torque channel `send_action` declines to use.
    """
    from lerobot.motors.damiao.damiao import DamiaoMotorsBus

    signature = inspect.signature(DamiaoMotorsBus._mit_control_batch)
    annotation = str(signature.parameters["commands"].annotation)
    floats = annotation.count("float")
    ok = "tuple[" in annotation and floats >= 5
    return FactResult(
        ok=ok,
        expected="_mit_control_batch commands value is a 5-float MIT tuple (torque channel open)",
        actual=f"commands annotation = {annotation}",
    )


def use_velocity_and_torque_default_false() -> FactResult:
    """`16` §11 #1 — `use_velocity_and_torque` defaults to False on the follower config."""
    default = _dataclass_field_default(
        "lerobot.robots.openarm_follower", "OpenArmFollowerConfig", "use_velocity_and_torque"
    )
    ok = default is False
    return FactResult(
        ok=ok,
        expected="OpenArmFollowerConfig.use_velocity_and_torque default is False",
        actual=f"default = {default!r}",
    )


def side_default_requires_explicit() -> FactResult:
    """`16` §11 #2 — `side` has no operative default; unspecified collapses joint_limits."""
    default = _dataclass_field_default(
        "lerobot.robots.openarm_follower", "OpenArmFollowerConfig", "side"
    )
    ok = default is None
    return FactResult(
        ok=ok,
        expected="OpenArmFollowerConfig.side default is None (must be set to left/right)",
        actual=f"default = {default!r}",
    )


def max_relative_target_default_off() -> FactResult:
    """`16` §11 #7 — LeRobot's only slew guard, `max_relative_target`, defaults OFF (None)."""
    default = _dataclass_field_default(
        "lerobot.robots.openarm_follower", "OpenArmFollowerConfig", "max_relative_target"
    )
    ok = default is None
    return FactResult(
        ok=ok,
        expected="OpenArmFollowerConfig.max_relative_target default is None (slew guard off)",
        actual=f"default = {default!r}",
    )


def cameras_default_empty_dict() -> FactResult:
    """`16` §10.2 — the camera contract is an empty dict the user fills in."""
    default = _dataclass_field_default(
        "lerobot.robots.openarm_follower", "OpenArmFollowerConfig", "cameras"
    )
    ok = default == {}
    return FactResult(
        ok=ok,
        expected="OpenArmFollowerConfig.cameras default_factory yields {}",
        actual=f"default = {default!r}",
    )


def socketcan_no_bitrate_param() -> FactResult:
    """`16` §10.1 — SocketcanBus takes no bitrate/data_bitrate; only `fd` acts on the socket."""
    from can.interfaces.socketcan import SocketcanBus

    params = set(inspect.signature(SocketcanBus.__init__).parameters)
    ok = "bitrate" not in params and "data_bitrate" not in params and "fd" in params
    return FactResult(
        ok=ok,
        expected="SocketcanBus.__init__ exposes fd but neither bitrate nor data_bitrate",
        actual=f"params = {sorted(params - {'self'})}",
    )


def max_state_dim_default_32() -> FactResult:
    """`10` FR-TRN-064 — the policy state pad width defaults to 32."""
    default = _dataclass_field_default(
        "lerobot.policies.smolvla.configuration_smolvla", "SmolVLAConfig", "max_state_dim"
    )
    ok = default == 32
    return FactResult(
        ok=ok,
        expected="SmolVLAConfig.max_state_dim default is 32",
        actual=f"default = {default!r}",
    )


def kinematics_unconstrained_fallback() -> FactResult:
    """`16` §11 #6 — the IK solver retries with `limits=[]` on NoSolutionFound.

    A solution found on that retry has thrown away the joint limits, which is the
    silent-failure `FR-OPS-043` disables by default.
    """
    kinematics = importlib.import_module("openarm_control.kinematics")
    solver = kinematics._IKSolver
    source = inspect.getsource(solver.solve)
    ok = "limits=[]" in source.replace(" ", "") and "NoSolutionFound" in source
    return FactResult(
        ok=ok,
        expected="_IKSolver.solve retries solve_ik with limits=[] inside a NoSolutionFound handler",
        actual=("limits=[] unconstrained retry present" if ok else "no unconstrained retry found"),
    )


def make_robot_from_config_hardcoded_openarm() -> FactResult:
    """`16` §10.1 D-1 — OpenArm is a first-class LeRobot robot via a hardcoded branch."""
    utils = importlib.import_module("lerobot.robots.utils")
    follower = importlib.import_module("lerobot.robots.openarm_follower")
    bimanual = importlib.import_module("lerobot.robots.bi_openarm_follower")
    has_factory = callable(getattr(utils, "make_robot_from_config", None))
    ok = (
        has_factory
        and isinstance(getattr(follower, "OpenArmFollower", None), type)
        and isinstance(getattr(bimanual, "BiOpenArmFollower", None), type)
    )
    return FactResult(
        ok=ok,
        expected="make_robot_from_config exists; OpenArmFollower and BiOpenArmFollower are classes",
        actual=f"make_robot_from_config callable={has_factory}; follower/bimanual classes present",
    )


def chunk_size_threshold_default_half() -> FactResult:
    """`16` §10.2 — async `chunk_size_threshold` defaults 0.5; `actions_per_chunk` is required."""
    threshold = _dataclass_field_default(
        "lerobot.async_inference.configs", "RobotClientConfig", "chunk_size_threshold"
    )
    per_chunk = _dataclass_field_default(
        "lerobot.async_inference.configs", "RobotClientConfig", "actions_per_chunk"
    )
    ok = threshold == 0.5 and per_chunk is dataclasses.MISSING
    per_chunk_state = "required" if per_chunk is dataclasses.MISSING else repr(per_chunk)
    return FactResult(
        ok=ok,
        expected="RobotClientConfig.chunk_size_threshold default 0.5; actions_per_chunk required",
        actual=f"chunk_size_threshold={threshold!r}, actions_per_chunk={per_chunk_state}",
    )


PREDICATES: dict[str, Callable[[], FactResult]] = {
    "send_action_tau_dq_zero_hardcode": send_action_tau_dq_zero_hardcode,
    "mit_control_batch_accepts_tau": mit_control_batch_accepts_tau,
    "use_velocity_and_torque_default_false": use_velocity_and_torque_default_false,
    "side_default_requires_explicit": side_default_requires_explicit,
    "max_relative_target_default_off": max_relative_target_default_off,
    "cameras_default_empty_dict": cameras_default_empty_dict,
    "socketcan_no_bitrate_param": socketcan_no_bitrate_param,
    "max_state_dim_default_32": max_state_dim_default_32,
    "kinematics_unconstrained_fallback": kinematics_unconstrained_fallback,
    "make_robot_from_config_hardcoded_openarm": make_robot_from_config_hardcoded_openarm,
    "chunk_size_threshold_default_half": chunk_size_threshold_default_half,
}


def resolve(predicate_name: str) -> Callable[[], FactResult]:
    """Return the predicate callable a fact names.

    Args:
        predicate_name: The `check_predicate` value from `upstream_facts.yaml`.

    Returns:
        (Callable[[], FactResult]) The predicate.

    Raises:
        KeyError: When no predicate by that name exists — a fact that cites a
            predicate the checker does not implement is a defect, not a pass.
    """
    return PREDICATES[predicate_name]


SEVERITY_FAIL_BLOCKING = "FAIL_BLOCKING"


@dataclass(frozen=True)
class FactRow:
    """One fact's checked outcome, carrying the acceptance ⑤ report fields.

    Attributes:
        fact_id: The fact identifier from `upstream_facts.yaml`.
        ok: True when the installed upstream still matches.
        severity: Violation grade declared for the fact.
        expected: What the fact asserts.
        actual: What introspection found.
        affected_frs: Requirements that lose their ground when the fact fails.
    """

    fact_id: str
    ok: bool
    severity: str
    expected: str
    actual: str
    affected_frs: tuple[str, ...]

    def as_line(self) -> str:
        """Render the row as one report line.

        Returns:
            (str) `PASS`/`FAIL` line with the four acceptance-⑤ fields on failure.
        """
        if self.ok:
            return f"PASS  {self.fact_id}"
        return (
            f"FAIL  {self.fact_id} [{self.severity}] "
            f"expected={self.expected!r} actual={self.actual!r} affected={list(self.affected_frs)}"
        )


def run_facts(facts_document: dict[str, object]) -> list[FactRow]:
    """Evaluate every fact in a parsed `upstream_facts.yaml` against the pin.

    A fact naming an unknown predicate is a hard failure, not a skip: an unchecked
    citation is exactly the gap this checker exists to close.

    Args:
        facts_document: Parsed `upstream_facts.yaml`.

    Returns:
        (list[FactRow]) One row per declared fact, in document order.
    """
    rows: list[FactRow] = []
    facts = facts_document.get("facts", [])
    if not isinstance(facts, list):
        raise TypeError("upstream_facts.yaml 'facts' is not a list")
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("fact_id", "?"))
        severity = str(fact.get("severity", "HIGH"))
        affected = tuple(str(fr) for fr in (fact.get("affected_frs") or []))
        predicate_name = str(fact.get("check_predicate", ""))
        try:
            predicate = resolve(predicate_name)
        except KeyError:
            rows.append(
                FactRow(
                    fact_id=fact_id,
                    ok=False,
                    severity=SEVERITY_FAIL_BLOCKING,
                    expected=f"a predicate named {predicate_name!r}",
                    actual="no such predicate implemented",
                    affected_frs=affected,
                )
            )
            continue
        result = predicate()
        rows.append(
            FactRow(
                fact_id=fact_id,
                ok=result.ok,
                severity=severity,
                expected=result.expected,
                actual=result.actual,
                affected_frs=affected,
            )
        )
    return rows
