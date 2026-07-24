"""Input-stage parameter validation for the three inference backends (`FR-INF-016/017/019`).

The load-bearing word is **input-stage**: `11` §3.3 requires the illegal-parameter
rejection to fire *before* the LeRobot config object is constructed, not as the
`ValueError` that `configuration_rtc.py:38-48` (and `configuration_act.py`'s
`__post_init__`, and `RobotClientConfig`'s missing-argument error) would raise on
construction. Front-running those points is what lets the UI show a reason the
operator can act on, and — for `actions_per_chunk` — what stops a stale `50` from
being prefilled to paper over a missing required argument.

Each rejection carries a distinct `InferenceParamReason`, never a merged "invalid
config", so a caller (and CG-4A-07a/b/c) can assert *which* rule fired. The defaults
here are the frozen `FR-INF-016/017/019` values; the one field with **no default is
`RemoteParams.actions_per_chunk`** — that absence is the contract (`FR-INF-019`), and
`validate_remote_params` refuses `None` rather than substituting a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# FR-INF-016 RTC defaults. `execution_horizon`=10, `max_guidance_weight`=10.0 (must be
# > 0), `queue_threshold`=30, prefix schedule LINEAR. The schedule set mirrors LeRobot's
# `RTCAttentionSchedule` enum; it is restated here as a frozen contract value so the
# input-stage validator needs no torch-bearing import to run.
RTC_EXECUTION_HORIZON_DEFAULT = 10
RTC_MAX_GUIDANCE_WEIGHT_DEFAULT = 10.0
RTC_QUEUE_THRESHOLD_DEFAULT = 30
RTC_PREFIX_SCHEDULE_DEFAULT = "LINEAR"
RTC_PREFIX_SCHEDULES: frozenset[str] = frozenset({"ZEROS", "ONES", "LINEAR", "EXP"})

# FR-INF-017 ACT defaults. `chunk_size`=100, `n_action_steps`=100, and temporal
# ensembling off (`temporal_ensemble_coeff`=None). When ensembling IS set, LeRobot
# forces `n_action_steps`=1; that constraint is checked, not silently applied.
ACT_CHUNK_SIZE_DEFAULT = 100
ACT_N_ACTION_STEPS_DEFAULT = 100

# FR-INF-019 remote defaults — `chunk_size_threshold`=0.5, aggregate `weighted_average`.
# The four aggregate names mirror LeRobot's `AGGREGATE_FUNCTIONS` keys. There is
# deliberately NO `actions_per_chunk` default (see module docstring).
REMOTE_CHUNK_SIZE_THRESHOLD_DEFAULT = 0.5
REMOTE_AGGREGATE_FN_DEFAULT = "weighted_average"
REMOTE_AGGREGATE_FN_NAMES: frozenset[str] = frozenset(
    {"weighted_average", "latest_only", "average", "conservative"}
)


class InferenceParamReason(Enum):
    """The distinct reason each parameter rejection carries.

    Distinctness is the contract: CG-4A-07a/b/c assert a specific rule fired, so a
    merged "config invalid" would defeat the gate. Each value names exactly one
    violated rule.
    """

    RTC_GUIDANCE_WEIGHT_NONPOSITIVE = "rtc_guidance_weight_nonpositive"
    RTC_SCHEDULE_UNKNOWN = "rtc_schedule_unknown"
    RTC_EXECUTION_HORIZON_NONPOSITIVE = "rtc_execution_horizon_nonpositive"
    RTC_QUEUE_THRESHOLD_NEGATIVE = "rtc_queue_threshold_negative"
    ACT_TEMPORAL_ENSEMBLE_ACTION_STEPS = "act_temporal_ensemble_action_steps"
    ACT_ACTION_STEPS_EXCEED_CHUNK = "act_action_steps_exceed_chunk"
    REMOTE_ACTIONS_PER_CHUNK_MISSING = "remote_actions_per_chunk_missing"
    REMOTE_ACTIONS_PER_CHUNK_NONPOSITIVE = "remote_actions_per_chunk_nonpositive"
    REMOTE_CHUNK_THRESHOLD_RANGE = "remote_chunk_threshold_range"
    REMOTE_AGGREGATE_FN_UNKNOWN = "remote_aggregate_fn_unknown"
    RELATIVE_ACTION_REQUIRES_RTC = "relative_action_requires_rtc"


class InferenceParamError(ValueError):
    """An input-stage rejection, raised before any LeRobot config is constructed.

    Carries the machine-readable `reason` so a caller can branch on the exact rule
    and the UI can display why the input was refused. Being raised at the input
    stage is the whole point (CG-4A-07a): it precedes, rather than wraps, the
    `ValueError` the LeRobot config would raise on construction.
    """

    def __init__(self, reason: InferenceParamReason, message: str) -> None:
        """Bind the reason to a human message.

        Args:
            reason: The distinct rule that was violated.
            message: A sentence naming the offending value.
        """
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class RtcParams:
    """RTC inference parameters (`FR-INF-016`), defaulted to the frozen values.

    Attributes:
        execution_horizon: Overlap horizon between chunks (default 10).
        prefix_attention_schedule: One of `RTC_PREFIX_SCHEDULES` (default LINEAR).
        max_guidance_weight: RTC guidance weight; must be > 0 (default 10.0).
        queue_threshold: Refill low-watermark — a new chunk is generated when the
            leftover action-queue size drops to `<= queue_threshold` (Q9 confirmed,
            default 30). This is NOT the exhaustion threshold (that is qsize == 0).
    """

    execution_horizon: int = RTC_EXECUTION_HORIZON_DEFAULT
    prefix_attention_schedule: str = RTC_PREFIX_SCHEDULE_DEFAULT
    max_guidance_weight: float = RTC_MAX_GUIDANCE_WEIGHT_DEFAULT
    queue_threshold: int = RTC_QUEUE_THRESHOLD_DEFAULT


@dataclass(frozen=True)
class ActParams:
    """ACT inference parameters (`FR-INF-017`), defaulted to the frozen values.

    Attributes:
        chunk_size: Action-chunk upper bound (default 100).
        n_action_steps: Action steps executed per policy call (default 100). Must be
            1 when temporal ensembling is set, and never exceed `chunk_size`.
        temporal_ensemble_coeff: Temporal-ensembling coefficient, or None (default)
            for no ensembling.
    """

    chunk_size: int = ACT_CHUNK_SIZE_DEFAULT
    n_action_steps: int = ACT_N_ACTION_STEPS_DEFAULT
    temporal_ensemble_coeff: float | None = None


@dataclass(frozen=True)
class RemoteParams:
    """Remote-gRPC inference parameters (`FR-INF-019`).

    `actions_per_chunk` has **no default**: `FR-INF-019` makes it a required argument
    with no fallback, and the stale official `50` must never be prefilled. `None`
    means the operator supplied nothing, and `validate_remote_params` refuses it.

    Attributes:
        actions_per_chunk: Actions the server returns per chunk. Required; None means
            not supplied and is rejected (never defaulted to 50).
        chunk_size_threshold: Client refill threshold in [0, 1] (default 0.5).
        aggregate_fn_name: One of `REMOTE_AGGREGATE_FN_NAMES` (default weighted_average).
        server_address: The `policy_server` address the client connects to.
        fps: Control rate, used only to compute the `NFR-INF-001` advisory bound.
    """

    actions_per_chunk: int | None = None
    chunk_size_threshold: float = REMOTE_CHUNK_SIZE_THRESHOLD_DEFAULT
    aggregate_fn_name: str = REMOTE_AGGREGATE_FN_DEFAULT
    server_address: str = "localhost:8080"
    fps: int = 30


@dataclass(frozen=True)
class PolicyProfile:
    """What the factory needs to know about a loaded checkpoint to gate a backend.

    A real LeRobot policy exposes these through its config and preprocessor steps
    (relative-action is an enabled `RelativeActionsProcessorStep`); this is the
    minimal projection the input-stage checks read, so the offline gates need no
    model weights.

    Attributes:
        policy_type: `act` / `pi0` / `pi05` / `smolvla` / ... (informational here).
        relative_action: Whether the policy emits relative actions. A relative-action
            policy is incompatible with `sync` (`FR-INF-015`): `sync` is blocked and
            RTC forced.
    """

    policy_type: str
    relative_action: bool = False


def validate_rtc_params(params: RtcParams) -> None:
    """Reject illegal RTC parameters at the input stage (`FR-INF-016`, CG-4A-07a).

    Fires before a LeRobot `RTCConfig` is constructed, so `max_guidance_weight <= 0`
    is caught here rather than by `configuration_rtc.py`'s `ValueError`.

    Args:
        params: The RTC parameters to check.

    Raises:
        InferenceParamError: On a non-positive guidance weight, an unknown prefix
            schedule, a non-positive execution horizon, or a negative queue threshold.
    """
    if params.max_guidance_weight <= 0:
        raise InferenceParamError(
            InferenceParamReason.RTC_GUIDANCE_WEIGHT_NONPOSITIVE,
            "max_guidance_weight must be > 0 (FR-INF-016); "
            f"got {params.max_guidance_weight}. Rejected at the input stage, before "
            "LeRobot's configuration_rtc ValueError.",
        )
    if params.prefix_attention_schedule not in RTC_PREFIX_SCHEDULES:
        raise InferenceParamError(
            InferenceParamReason.RTC_SCHEDULE_UNKNOWN,
            f"prefix_attention_schedule must be one of {sorted(RTC_PREFIX_SCHEDULES)}; "
            f"got {params.prefix_attention_schedule!r}.",
        )
    if params.execution_horizon <= 0:
        raise InferenceParamError(
            InferenceParamReason.RTC_EXECUTION_HORIZON_NONPOSITIVE,
            f"execution_horizon must be > 0; got {params.execution_horizon}.",
        )
    if params.queue_threshold < 0:
        raise InferenceParamError(
            InferenceParamReason.RTC_QUEUE_THRESHOLD_NEGATIVE,
            f"queue_threshold must be >= 0; got {params.queue_threshold}.",
        )


def validate_act_params(params: ActParams) -> None:
    """Reject illegal ACT parameters at the input stage (`FR-INF-017`, CG-4A-07c).

    Mirrors the two constraints LeRobot's `configuration_act.py.__post_init__`
    enforces, but at the input stage and with a distinct reason each: temporal
    ensembling forces `n_action_steps == 1`, and `n_action_steps` may not exceed
    `chunk_size`.

    Args:
        params: The ACT parameters to check.

    Raises:
        InferenceParamError: When ensembling is set with `n_action_steps != 1`, or
            when `n_action_steps > chunk_size`.
    """
    if params.temporal_ensemble_coeff is not None and params.n_action_steps != 1:
        raise InferenceParamError(
            InferenceParamReason.ACT_TEMPORAL_ENSEMBLE_ACTION_STEPS,
            "temporal_ensemble_coeff is set, so n_action_steps must be 1 "
            f"(FR-INF-017); got n_action_steps={params.n_action_steps}. The policy "
            "must be queried every step to ensemble.",
        )
    if params.n_action_steps > params.chunk_size:
        raise InferenceParamError(
            InferenceParamReason.ACT_ACTION_STEPS_EXCEED_CHUNK,
            "n_action_steps must not exceed chunk_size (FR-INF-017); got "
            f"n_action_steps={params.n_action_steps}, chunk_size={params.chunk_size}.",
        )


def validate_remote_params(params: RemoteParams) -> None:
    """Reject illegal remote-gRPC parameters at the input stage (`FR-INF-019`, CG-4A-07b).

    The primary rule is that `actions_per_chunk` is required with no fallback: a
    missing value refuses startup rather than being prefilled with the stale `50`.

    Args:
        params: The remote parameters to check.

    Raises:
        InferenceParamError: When `actions_per_chunk` is missing or non-positive, the
            `chunk_size_threshold` is outside [0, 1], or the aggregate function name
            is unknown.
    """
    if params.actions_per_chunk is None:
        raise InferenceParamError(
            InferenceParamReason.REMOTE_ACTIONS_PER_CHUNK_MISSING,
            "actions_per_chunk is required and has no default (FR-INF-019); startup is "
            "refused. It is NOT prefilled — the official 50 is stale. Enter the value "
            "your policy emits per chunk.",
        )
    if params.actions_per_chunk <= 0:
        raise InferenceParamError(
            InferenceParamReason.REMOTE_ACTIONS_PER_CHUNK_NONPOSITIVE,
            f"actions_per_chunk must be > 0; got {params.actions_per_chunk}.",
        )
    if not 0 <= params.chunk_size_threshold <= 1:
        raise InferenceParamError(
            InferenceParamReason.REMOTE_CHUNK_THRESHOLD_RANGE,
            f"chunk_size_threshold must be in [0, 1]; got {params.chunk_size_threshold}.",
        )
    if params.aggregate_fn_name not in REMOTE_AGGREGATE_FN_NAMES:
        raise InferenceParamError(
            InferenceParamReason.REMOTE_AGGREGATE_FN_UNKNOWN,
            f"aggregate_fn_name must be one of {sorted(REMOTE_AGGREGATE_FN_NAMES)}; "
            f"got {params.aggregate_fn_name!r}.",
        )


def advisory_max_roundtrip_sec(
    chunk_size_threshold: float, actions_per_chunk: int, fps: float
) -> float:
    """Compute the `NFR-INF-001` async-chunking round-trip bound the inputs imply.

    `NFR-INF-001`: p99 inference round-trip must be
    `<= (chunk_size_threshold * actions_per_chunk) / fps` seconds. This is the
    "계산 보조" the CG-4A-07b negative branch mandates in place of a prefill: given the
    operator's `fps`/`threshold`/`actions_per_chunk`, it returns the satisfying
    bound to *display*, and it never writes a value into any input field.

    Args:
        chunk_size_threshold: The client refill threshold in [0, 1].
        actions_per_chunk: The operator-supplied chunk size.
        fps: The control rate.

    Returns:
        (float) The p99 round-trip bound in seconds.

    Raises:
        ValueError: If `fps <= 0` (the bound is undefined).
    """
    if fps <= 0:
        raise ValueError(f"fps must be > 0 to compute the round-trip bound; got {fps}")
    return (chunk_size_threshold * actions_per_chunk) / fps
