"""WP-4B-05 — the upstream-fact predicates the 4A/4B band depends on.

`02c` §2.5 (`FR-OPS-089`): every LeRobot-internal fact that a 4A/4B deliverable is
built on is checked by importing the pinned upstream and inspecting a real symbol —
a bound function's source, a dataclass default, or the function's own output — never
by matching a file's text at a line number. Each predicate returns the Wave 0-Env
checker's own `FactResult`, so `registry.env.upstream.run_facts` executes these
exactly as it executes its own eleven; this module supplies predicates, not a
second checker.

The predicates here are the ones the committed Wave 0-Env checker does not already
carry: items (a)/(c)/(f)/(g) of `FR-OPS-089` plus the four extra premises `02c`
§2.5 assigns to this band. Items (b)/(d)/(e) and `max_state_dim` are already in
`registry.env.upstream`; this band references those by name rather than restating
them (`contract_regression_facts.yaml`).

Heavy imports sit inside each predicate — matching `registry.env.upstream` — so
this module imports for name resolution even where the robot stack is absent, and
`registry.check`'s light lane never pulls torch/lerobot.

The EXPECTED values live here as named constants on purpose. `02c` §2.1 ⑥ is
explicit: a value copied out of LeRobot (`max_state_dim`, the RTC defaults) must be
registered as a contract-regression item so that **when the copied value drifts,
deployment stops**. This module is that registration point, so the constant and the
drift-detector are the same object — which is the opposite of a silent hardcode.
"""

from __future__ import annotations

import dataclasses
import inspect

from registry.env.upstream import FactResult

# `FR-TRN-064` — SmolVLA pads observation.state and action to 32. `max_state_dim`
# is already guarded by the Wave 0-Env checker; this band adds the action half so
# the pair the policy matrix (WP-4B-01) reads from the config is complete.
MAX_ACTION_DIM_EXPECTED = 32

# `FR-INF-016` RTC defaults (WP-4A-07 froze these as its input-stage contract). If
# any drifts upstream, WP-4A-07's restated constants lie silently, so all four are
# one registration item — a single drift blocks deployment.
RTC_EXECUTION_HORIZON_EXPECTED = 10
RTC_MAX_GUIDANCE_WEIGHT_EXPECTED = 10.0
RTC_PREFIX_SCHEDULE_EXPECTED = "LINEAR"
RTC_SCHEDULE_MEMBERS_EXPECTED = ("ZEROS", "ONES", "LINEAR", "EXP")

# The observation.state flatten rule (`FR-TRN-061`) is verified behaviourally: N
# scalar joint features must collapse into exactly one `observation.state` vector of
# width N. Three is an arbitrary probe width chosen to distinguish a flatten (one
# key, shape (3,)) from a per-joint expansion (three keys).
FLATTEN_PROBE_JOINT_COUNT = 3


def _field_default(cls: type, field_name: str) -> object:
    """Return a dataclass field's declared default, or its factory's product.

    A field with neither default nor factory is required; this returns
    `dataclasses.MISSING` for it, which is how a "must be set" contract (e.g.
    `EvalPipelineConfig.env`) is distinguished from one defaulting to `None`.

    Args:
        cls: The dataclass to read.
        field_name: The field whose default is wanted.

    Returns:
        (object) The default, the factory's product, `dataclasses.MISSING` when
            required, or a sentinel string when the field is absent.
    """
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


def connect_calls_set_zero_position() -> FactResult:
    """`FR-OPS-089` (a) — `OpenArmFollower.connect()` still calls `set_zero_position()`.

    Auto-zeroing on connect is the premise Wave 1's calibration and every
    downstream limit rest on. If a LeRobot upgrade drops the call, the arm connects
    at an undefined zero and every joint limit is silently in the wrong frame.
    """
    from lerobot.robots.openarm_follower import OpenArmFollower

    source = inspect.getsource(OpenArmFollower.connect)
    calls = "set_zero_position" in source
    return FactResult(
        ok=calls,
        expected="OpenArmFollower.connect() calls set_zero_position()",
        actual="set_zero_position() call present" if calls else "no set_zero_position() call found",
    )


def push_to_hub_default_true() -> FactResult:
    """`FR-TRN-070`/`FR-TRN-075`/`FR-OPS-082` (c) — `DatasetRecordConfig.push_to_hub` defaults True.

    The closed-network guard exists precisely because the upstream default uploads.
    If upstream flipped the default to False the guard would be dead code guarding
    nothing — the regression must notice the premise moved, not silently agree.
    """
    from lerobot.configs.dataset import DatasetRecordConfig

    default = _field_default(DatasetRecordConfig, "push_to_hub")
    ok = default is True
    return FactResult(
        ok=ok,
        expected="DatasetRecordConfig.push_to_hub default is True (closed-net must force False)",
        actual=f"default = {default!r}",
    )


def follower_feature_keysets_stable() -> FactResult:
    """`FR-OPS-089` (f) — action features are motors-only; observation merges motors + cameras.

    The two feature dicts define the LeRobot dataset column keyset. `action_features`
    must stay the motor set alone and `observation_features` must stay the motors ∪
    cameras merge; a change to either composition rewrites what a recorded dataset
    means, which no shape check downstream would catch.
    """
    from lerobot.robots.openarm_follower import OpenArmFollower

    action_source = inspect.getsource(OpenArmFollower.action_features.func)
    observation_source = inspect.getsource(OpenArmFollower.observation_features.func)
    action_motors_only = "_motors_ft" in action_source and "_cameras_ft" not in action_source
    observation_merges = "_motors_ft" in observation_source and "_cameras_ft" in observation_source
    ok = action_motors_only and observation_merges
    return FactResult(
        ok=ok,
        expected="action_features = motors only; observation_features = motors ∪ cameras",
        actual=(
            f"action motors-only={action_motors_only}, observation merges motors+cameras="
            f"{observation_merges}"
        ),
    )


def feature_utils_observation_state_flatten() -> FactResult:
    """`FR-OPS-089` (g)/`FR-TRN-061` — joint features flatten into one `observation.state` vector.

    Called behaviourally rather than read as text: N scalar joint features under the
    `observation` prefix must yield exactly `{observation.state: shape (N,), names=[...]}`,
    and under the `action` prefix exactly `{action: shape (N,)}`. A per-joint
    expansion (one key per joint) would break the state_dim==len(names) contract the
    dataset preflight (WP-4A-02) enforces.
    """
    from lerobot.utils.feature_utils import hw_to_dataset_features

    joints = {f"j{index}": float for index in range(FLATTEN_PROBE_JOINT_COUNT)}
    joint_names = list(joints)
    observation = hw_to_dataset_features(joints, "observation")
    action = hw_to_dataset_features(joints, "action")
    observation_ok = (
        list(observation) == ["observation.state"]
        and observation["observation.state"]["shape"] == (FLATTEN_PROBE_JOINT_COUNT,)
        and observation["observation.state"]["names"] == joint_names
    )
    action_ok = list(action) == ["action"] and action["action"]["shape"] == (
        FLATTEN_PROBE_JOINT_COUNT,
    )
    ok = observation_ok and action_ok
    return FactResult(
        ok=ok,
        expected=(
            f"{FLATTEN_PROBE_JOINT_COUNT} joints -> one observation.state of shape "
            f"({FLATTEN_PROBE_JOINT_COUNT},) and one action of the same width"
        ),
        actual=f"observation keys={list(observation)}; action keys={list(action)}",
    )


def max_action_dim_default_32() -> FactResult:
    """`FR-TRN-064` — the policy action pad width defaults to 32.

    The action half of the `max_state_dim`/`max_action_dim` pair WP-4B-01 reads from
    the config rather than copying. Registered so a copied 32 that drifts stops the
    deployment (`02c` §2.1 ⑥).
    """
    from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig

    default = _field_default(SmolVLAConfig, "max_action_dim")
    ok = default == MAX_ACTION_DIM_EXPECTED
    return FactResult(
        ok=ok,
        expected=f"SmolVLAConfig.max_action_dim default is {MAX_ACTION_DIM_EXPECTED}",
        actual=f"default = {default!r}",
    )


def normalize_processor_denom_std_plus_eps() -> FactResult:
    """WP-4A-03 premise — `NormalizerProcessorStep` normalizes with `denom = std + eps`.

    The degenerate-channel detector estimates amplification assuming the divisor is
    `std + eps`, not `max(std, eps)` or a clamped form. If upstream changes the
    denominator the amplification estimate is computed against the wrong divisor and
    silently mis-flags channels.
    """
    from lerobot.processor.normalize_processor import NormalizerProcessorStep

    # `_apply_transform` is inherited from the normalization mixin, so introspect the
    # resolved method rather than the subclass body (which does not contain it).
    source = inspect.getsource(NormalizerProcessorStep._apply_transform).replace(" ", "")
    present = "denom=std+self.eps" in source and "(tensor-mean)/denom" in source
    return FactResult(
        ok=present,
        expected="NormalizerProcessorStep normalizes mean/std by denom = std + self.eps",
        actual="denom = std + self.eps divisor present" if present else "denominator form changed",
    )


def rollout_rtc_defaults() -> FactResult:
    """`FR-INF-016` — the four RTC defaults WP-4A-07 froze still hold upstream.

    `execution_horizon`=10, `max_guidance_weight`=10.0, `prefix_attention_schedule`
    =LINEAR, and the schedule enum is exactly {ZEROS, ONES, LINEAR, EXP}. One
    registration item covering four values: any single drift fails it, which is the
    intended coupling — WP-4A-07 restates all four as constants and a divergence
    would make those constants lie.
    """
    from lerobot.rollout.inference.rtc import RTCConfig

    horizon = _field_default(RTCConfig, "execution_horizon")
    guidance = _field_default(RTCConfig, "max_guidance_weight")
    schedule = _field_default(RTCConfig, "prefix_attention_schedule")
    schedule_name = getattr(schedule, "name", schedule)
    # The schedule enum is whatever type RTCConfig's default carries, so the member
    # set is read from that type's `__members__` (ordered name->member) rather than
    # from a second import that could drift.
    schedule_members: dict[str, object] = getattr(type(schedule), "__members__", {})
    members = tuple(schedule_members)
    ok = (
        horizon == RTC_EXECUTION_HORIZON_EXPECTED
        and guidance == RTC_MAX_GUIDANCE_WEIGHT_EXPECTED
        and schedule_name == RTC_PREFIX_SCHEDULE_EXPECTED
        and members == RTC_SCHEDULE_MEMBERS_EXPECTED
    )
    return FactResult(
        ok=ok,
        expected=(
            f"RTCConfig: execution_horizon={RTC_EXECUTION_HORIZON_EXPECTED}, "
            f"max_guidance_weight={RTC_MAX_GUIDANCE_WEIGHT_EXPECTED}, "
            f"prefix_attention_schedule={RTC_PREFIX_SCHEDULE_EXPECTED}, "
            f"schedule members={RTC_SCHEDULE_MEMBERS_EXPECTED}"
        ),
        actual=(
            f"execution_horizon={horizon!r}, max_guidance_weight={guidance!r}, "
            f"prefix_attention_schedule={schedule_name!r}, members={members}"
        ),
    )


def eval_pipeline_env_required() -> FactResult:
    """4C premise (`02c` §3.0) — `EvalPipelineConfig.env` is required, not defaulted.

    The 4C real-robot eval harness relies on `env` having no default, so a
    configuration that omits it is refused at parse time rather than silently
    running against a default environment. If upstream gives `env` a default, that
    refusal disappears and 4C's premise is gone.
    """
    from lerobot.configs.eval import EvalPipelineConfig

    default = _field_default(EvalPipelineConfig, "env")
    ok = default is dataclasses.MISSING
    state = "required (no default)" if ok else f"default = {default!r}"
    return FactResult(
        ok=ok,
        expected="EvalPipelineConfig.env has no default (must be supplied)",
        actual=state,
    )


# The predicates this band registers into the Wave 0-Env resolver table, keyed by
# the name each fact cites in `contract_regression_facts.yaml`. Names are distinct
# from `registry.env.upstream.PREDICATES` so registration never shadows a committed
# predicate (`register.register_predicates` refuses a collision).
ADDITIONAL_PREDICATES = {
    "connect_calls_set_zero_position": connect_calls_set_zero_position,
    "push_to_hub_default_true": push_to_hub_default_true,
    "follower_feature_keysets_stable": follower_feature_keysets_stable,
    "feature_utils_observation_state_flatten": feature_utils_observation_state_flatten,
    "max_action_dim_default_32": max_action_dim_default_32,
    "normalize_processor_denom_std_plus_eps": normalize_processor_denom_std_plus_eps,
    "rollout_rtc_defaults": rollout_rtc_defaults,
    "eval_pipeline_env_required": eval_pipeline_env_required,
}
