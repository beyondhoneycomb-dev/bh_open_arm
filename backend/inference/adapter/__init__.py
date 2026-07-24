"""WP-4A-07 — the inference-engine adapter (`sync` / `rtc` / remote gRPC).

The producer half of the runtime spine: it turns a policy into targets and — on the
in-process paths — **publishes** them to the `ActuationScheduler`'s mailbox, which is
the sole CAN writer (SPINE §2-1). This package invents no writer and re-implements no
gateway; it imports the committed `ActuationScheduler`, mailbox, and producer, and on
the remote path routes through the committed `send_action` override directly
(`NFR-INF-008`, `robot_client.py:381-383`).

Public surface:

- `InferenceBackend` — the closed set `{SYNC, RTC, REMOTE_GRPC}` (`FR-INF-015/019`).
- `build_inference_engine` — the factory; validates params at the input stage,
  applies the relative-action gate, gates on WP-4A-05 lineage, returns a session.
- `InferenceSession` — one held connection, switchable backends (`FR-INF-021`: switch
  resets state, keeps the connection), mailbox-only publishing, live queue metering.
- The input-stage validators and their typed reasons (`FR-INF-016/017/019`).
- `RemoteInferenceAdapter` + `ReVerificationHook` — the remote path and its honest
  Q8 deferral (the e2e remote rollout is unverified here and marked so, never faked).
- `find_actions_per_chunk_prefill` — the static no-50-prefill check (CG-4A-07b).
- `QueueMeter` — the exhaustion count/ratio and residual series (`FR-INF-012/020`).
"""

from __future__ import annotations

from backend.inference.adapter.backend_kind import InferenceBackend
from backend.inference.adapter.engine import (
    BackendNotPublishableError,
    BackendParams,
    InferenceSession,
)
from backend.inference.adapter.factory import build_inference_engine
from backend.inference.adapter.interpolator import ActionChunkQueue, ChunkInterpolator
from backend.inference.adapter.lerobot_config import build_rtc_config
from backend.inference.adapter.metering import QueueMeter
from backend.inference.adapter.params import (
    ActParams,
    InferenceParamError,
    InferenceParamReason,
    PolicyProfile,
    RemoteParams,
    RtcParams,
    advisory_max_roundtrip_sec,
    validate_act_params,
    validate_remote_params,
    validate_rtc_params,
)
from backend.inference.adapter.policy import (
    ChunkPolicy,
    action_vector_to_request,
    relative_action_from_preprocessor,
)
from backend.inference.adapter.remote import RemoteInferenceAdapter, ReVerificationHook
from backend.inference.adapter.static_check import (
    PrefillViolation,
    find_actions_per_chunk_prefill,
    scan_source,
)

__all__ = [
    "ActParams",
    "ActionChunkQueue",
    "BackendNotPublishableError",
    "BackendParams",
    "ChunkInterpolator",
    "ChunkPolicy",
    "InferenceBackend",
    "InferenceParamError",
    "InferenceParamReason",
    "InferenceSession",
    "PolicyProfile",
    "PrefillViolation",
    "QueueMeter",
    "ReVerificationHook",
    "RemoteInferenceAdapter",
    "RemoteParams",
    "RtcParams",
    "action_vector_to_request",
    "advisory_max_roundtrip_sec",
    "build_inference_engine",
    "build_rtc_config",
    "find_actions_per_chunk_prefill",
    "relative_action_from_preprocessor",
    "scan_source",
    "validate_act_params",
    "validate_remote_params",
    "validate_rtc_params",
]
