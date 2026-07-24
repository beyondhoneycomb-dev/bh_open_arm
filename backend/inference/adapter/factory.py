"""The inference-engine factory — one entry point, three backends, lineage-gated.

`FR-INF-015`/`019` and SHAPE-IM(3) call for three builders (sync+rtc / remote-gRPC /
param validator); this factory is where they converge into one call. It validates the
backend parameters at the input stage (via `InferenceSession.switch_backend`), applies
the relative-action gate, and returns a configured session whose active backend is the
requested one — the remote path lives inside the session as `remote_adapter`.

It also gates on WP-4A-05 lineage: a checkpoint may not drive the arm unless its
eight-element `LineageRecord` is complete (`lineage.validate()`), because an inference
engine that cannot say exactly which checkpoint — which dataset, stats, code SHA,
LeRobot version — it is serving cannot be reproduced or audited (`FR-TRN-054`,
`FR-OPS-071`). That call is the genuine consumption of the committed lineage record,
not a courtesy import.
"""

from __future__ import annotations

from backend.actuation import TargetMailbox
from backend.actuation.clock import Clock
from backend.inference.adapter.backend_kind import InferenceBackend
from backend.inference.adapter.engine import (
    DEFAULT_BASE_INFERENCE_LATENCY_SEC,
    BackendParams,
    InferenceSession,
)
from backend.inference.adapter.policy import ChunkPolicy
from backend.training.lineage import LineageRecord
from contracts.plugin.robot_abc import OpenArmRobot


def build_inference_engine(
    backend: InferenceBackend,
    robot: OpenArmRobot,
    mailbox: TargetMailbox,
    clock: Clock,
    policy: ChunkPolicy,
    params: BackendParams,
    fps: float,
    lineage: LineageRecord,
    base_inference_latency_sec: float = DEFAULT_BASE_INFERENCE_LATENCY_SEC,
) -> InferenceSession:
    """Build a lineage-gated inference session configured for `backend`.

    Validates the checkpoint's lineage (a served checkpoint must be reproducible),
    then constructs the session over the already-connected robot and switches it to
    the requested backend — which runs input-stage parameter validation and the
    relative-action gate.

    Args:
        backend: The backend to configure (`SYNC` / `RTC` / `REMOTE_GRPC`).
        robot: The already-connected follower; the session never reconnects it.
        mailbox: The publish-only channel the `ActuationScheduler` reads.
        clock: The shared clock producers stamp targets with.
        policy: The policy the session drives.
        params: Backend parameters (`ActParams` / `RtcParams` / `RemoteParams`).
        fps: Control rate; the RTC model's control period is `1 / fps`.
        lineage: The served checkpoint's eight-element lineage record (WP-4A-05).
        base_inference_latency_sec: Fixed per-chunk inference cost in the RTC model.

    Returns:
        (InferenceSession) The configured session; for `REMOTE_GRPC` its
        `remote_adapter` holds the validated remote adapter.

    Raises:
        LineageRecordError: If the checkpoint's lineage is incomplete (CG-4A-05a).
        InferenceParamError: On failed input-stage validation or the relative-action
            gate.
        TypeError: If `params` is the wrong type for `backend`.
    """
    lineage.validate()
    session = InferenceSession(
        robot=robot,
        mailbox=mailbox,
        clock=clock,
        policy=policy,
        fps=fps,
        base_inference_latency_sec=base_inference_latency_sec,
    )
    session.switch_backend(backend, params)
    return session
