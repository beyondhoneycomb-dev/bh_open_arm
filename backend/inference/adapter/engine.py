"""The inference session: one held connection, three switchable backends, mailbox-only publishing.

This is the object CG-4A-07e exercises. It holds a robot that the *caller* connected,
and it is structurally incapable of reconnecting it: nowhere does this class call
`robot.connect()` or `robot.disconnect()`. Switching backend (`switch_backend`) resets
the policy state, the action queue, and the interpolator (`FR-INF-021`) but touches
the connection not at all — because `connect()` unconditionally re-zeros the arm
(`FR-OPS-065/083`), so a reconnect on every switch would destroy the zero point
(SPINE §2-2). 100 switches therefore leave queue/interpolator residual 0 and the
`connect()` call count unchanged.

On the in-process paths (`SYNC`, `RTC`) the session is a **publisher**: it turns a
policy action into a `RequestedPositionAction` and publishes it to the `TargetMailbox`.
It never writes CAN — the committed `ActuationScheduler` is the sole writer, and it
reads that same mailbox. On the `REMOTE_GRPC` path the client calls `send_action()`
directly (`NFR-INF-008`), so the session delegates to a `RemoteInferenceAdapter` and
does not publish to the mailbox at all; ticking the publisher in that mode is refused.

The RTC path models the async producer/consumer deterministically: a logical
inference clock advances one control period per tick, a chunk becomes available one
inference-latency after it starts, and the queue is refilled at the `queue_threshold`
low-watermark (Q9). Determinism is deliberate — as with the actuation harness, "the
tick the queue starved" must be a reproducible fact a gate can assert (CG-4A-07f).
"""

from __future__ import annotations

from backend.actuation import MailboxProducer, TargetMailbox
from backend.actuation.clock import Clock
from backend.inference.adapter.backend_kind import InferenceBackend
from backend.inference.adapter.interpolator import ActionChunkQueue, ChunkInterpolator
from backend.inference.adapter.lerobot_config import build_rtc_config
from backend.inference.adapter.metering import QueueMeter
from backend.inference.adapter.params import (
    ActParams,
    InferenceParamError,
    InferenceParamReason,
    RemoteParams,
    RtcParams,
    validate_act_params,
    validate_remote_params,
)
from backend.inference.adapter.policy import ChunkPolicy, action_vector_to_request
from backend.inference.adapter.remote import RemoteInferenceAdapter
from contracts.action import RequestedPositionAction
from contracts.plugin.robot_abc import OpenArmRobot

# A fast policy by default: the offline throughput model is throttled by the delay
# injected on the dummy robot (CG-4A-07f), not by a fixed inference cost, so the base
# cost is zero unless a caller models a slow policy explicitly.
DEFAULT_BASE_INFERENCE_LATENCY_SEC = 0.0

# Intermediate targets the interpolator lays between two chunk actions. The default 1
# publishes chunk actions directly (no smoothing); a value > 1 smooths the published
# stream to the control rate, and is what makes a mid-interpolation residual observable
# for the switch-reset invariant (CG-4A-07e).
DEFAULT_INTERPOLATION_STEPS = 1

BackendParams = RtcParams | ActParams | RemoteParams


class BackendNotPublishableError(RuntimeError):
    """Raised when the mailbox publisher is ticked in `REMOTE_GRPC` mode.

    The remote client calls `send_action()` directly (`NFR-INF-008`); there is no
    mailbox target to publish in that mode, so ticking the publisher is a caller
    error, not a silent no-op. Use `remote_adapter` for the remote path.
    """


class InferenceSession:
    """One connection, three switchable backends; publishes to the mailbox, never CAN.

    Ownership: holds the robot (connected by the caller, never toggled here), the
    publish-only mailbox and its producer, the policy, the action queue, the
    interpolator, and the queue meter. The `ActuationScheduler` — not this session —
    owns the CAN writer and reads the mailbox.
    """

    def __init__(
        self,
        robot: OpenArmRobot,
        mailbox: TargetMailbox,
        clock: Clock,
        policy: ChunkPolicy,
        fps: float,
        base_inference_latency_sec: float = DEFAULT_BASE_INFERENCE_LATENCY_SEC,
        interpolation_steps: int = DEFAULT_INTERPOLATION_STEPS,
        producer_id: str = "inference-engine",
    ) -> None:
        """Wire the session over an already-connected robot.

        Args:
            robot: The follower providing observations and (on the remote path) the
                `send_action` gateway. The caller connects it; this session never
                calls `connect()`/`disconnect()`.
            mailbox: The publish-only channel the `ActuationScheduler` reads.
            clock: The shared clock producers stamp targets with.
            policy: The policy the session drives (`ChunkPolicy` surface).
            fps: Control rate; the RTC model's control period is `1 / fps`.
            base_inference_latency_sec: Fixed per-chunk inference cost in the RTC
                model, added to any delay injected on the robot.
            interpolation_steps: Intermediate targets laid between two chunk actions
                on the RTC path (>= 1; 1 publishes chunk actions directly).
            producer_id: Stable producer identity; unchanged across backend switches
                because the inference engine remains the same publisher (`FR-INF-021`).

        Raises:
            ValueError: If `fps <= 0` or `interpolation_steps < 1`.
        """
        if fps <= 0:
            raise ValueError(f"fps must be > 0; got {fps}")
        if interpolation_steps < 1:
            raise ValueError(f"interpolation_steps must be >= 1; got {interpolation_steps}")
        self._robot = robot
        self._mailbox = mailbox
        self._clock = clock
        self._policy = policy
        self._fps = fps
        self._dt = 1.0 / fps
        self._base_latency = base_inference_latency_sec
        self._interpolation_steps = interpolation_steps
        self._producer = MailboxProducer(producer_id, mailbox, clock)
        self._meter = QueueMeter()
        self._queue = ActionChunkQueue()
        self._interpolator = ChunkInterpolator()
        self._backend: InferenceBackend | None = None
        self._rtc_params: RtcParams | None = None
        self._act_params: ActParams | None = None
        self._remote_adapter: RemoteInferenceAdapter | None = None
        self._rtc_now = 0.0
        self._chunk_in_flight = False
        self._chunk_ready_at = 0.0
        self._last_published: RequestedPositionAction | None = None

    @property
    def backend(self) -> InferenceBackend | None:
        """The active backend, or None before the first `switch_backend`."""
        return self._backend

    @property
    def meter(self) -> QueueMeter:
        """The live queue meter (exhaustion count/ratio, residual series)."""
        return self._meter

    @property
    def queue_residual(self) -> int:
        """Actions still queued on the async path (0 on `SYNC`/`REMOTE_GRPC`)."""
        return self._queue.residual()

    @property
    def interpolator_residual(self) -> int:
        """Intermediate targets not yet emitted (0 unless mid-interpolation)."""
        return self._interpolator.residual()

    @property
    def remote_adapter(self) -> RemoteInferenceAdapter | None:
        """The remote adapter when in `REMOTE_GRPC` mode, else None."""
        return self._remote_adapter

    @property
    def last_published(self) -> RequestedPositionAction | None:
        """The most recently published target, or None."""
        return self._last_published

    def switch_backend(self, backend: InferenceBackend, params: BackendParams) -> None:
        """Switch the active backend, resetting state but keeping the connection (`FR-INF-021`).

        Validates `params` at the input stage for the target backend, applies the
        relative-action gate (`FR-INF-015`: a relative-action policy blocks `sync`),
        then resets policy state, the action queue, the interpolator, and the meter.
        It never calls `robot.connect()`/`disconnect()` — the connection is kept, so
        the arm's zero point survives the switch (SPINE §2-2).

        Args:
            backend: The backend to switch to.
            params: The parameters for that backend — `ActParams` for `SYNC`,
                `RtcParams` for `RTC`, `RemoteParams` for `REMOTE_GRPC`.

        Raises:
            InferenceParamError: On failed input-stage validation or a relative-action
                policy paired with `sync`.
            TypeError: If `params` is the wrong type for `backend`.
        """
        self._apply_relative_action_gate(backend)
        if backend is InferenceBackend.SYNC:
            if not isinstance(params, ActParams):
                raise self._param_type_error(backend, "ActParams", params)
            validate_act_params(params)
            self._act_params = params
            self._rtc_params = None
            self._remote_adapter = None
        elif backend is InferenceBackend.RTC:
            if not isinstance(params, RtcParams):
                raise self._param_type_error(backend, "RtcParams", params)
            # build_rtc_config validates at the input stage before LeRobot's config.
            build_rtc_config(params)
            self._rtc_params = params
            self._act_params = None
            self._remote_adapter = None
        else:
            if not isinstance(params, RemoteParams):
                raise self._param_type_error(backend, "RemoteParams", params)
            validate_remote_params(params)
            self._remote_adapter = RemoteInferenceAdapter(params, self._robot)
            self._rtc_params = None
            self._act_params = None
        self._backend = backend
        self._reset_runtime()

    def begin_episode(self) -> None:
        """Reset policy internal state and all buffers at episode start (`FR-INF-066`).

        Unlike a backend switch this also clears the meter, since exhaustion counts
        are per-episode. The connection is untouched here too.
        """
        self._reset_runtime()
        self._meter.reset()

    def sync_tick(self) -> RequestedPositionAction:
        """Run one inline `SYNC` tick: query the policy once and publish the target.

        Returns:
            (RequestedPositionAction) The published position request.

        Raises:
            BackendNotPublishableError: If the active backend is not `SYNC`.
        """
        if self._backend is not InferenceBackend.SYNC:
            raise BackendNotPublishableError(
                f"sync_tick requires the SYNC backend; active backend is {self._backend}"
            )
        observation = self._robot.get_observation()
        request = action_vector_to_request(self._policy.select_action(observation))
        self._producer.publish(request)
        self._last_published = request
        return request

    def rtc_tick(self) -> RequestedPositionAction | None:
        """Run one `RTC` tick of the deterministic async producer/consumer model.

        Completes any in-flight chunk whose inference latency has elapsed, refills at
        the `queue_threshold` low-watermark (Q9), then publishes one target. While the
        interpolator still has intermediate frames it emits those; only when a fresh
        chunk action is demanded does it meter the queue and pop one — so exhaustion
        (`FR-INF-012`) is measured exactly when the queue is the thing that ran dry. A
        starved tick publishes nothing (the scheduler holds).

        Returns:
            (RequestedPositionAction | None) The published target, or None when the
            queue was starved this tick.

        Raises:
            BackendNotPublishableError: If the active backend is not `RTC`.
        """
        if self._backend is not InferenceBackend.RTC or self._rtc_params is None:
            raise BackendNotPublishableError(
                f"rtc_tick requires the RTC backend; active backend is {self._backend}"
            )
        self._rtc_now += self._dt
        observation = self._robot.get_observation()
        injected_lag = float(getattr(self._robot, "last_observation_latency_sec", 0.0))
        latency = self._base_latency + injected_lag

        if self._chunk_in_flight and self._rtc_now >= self._chunk_ready_at:
            chunk = self._policy.predict_action_chunk(observation)
            self._queue.push_chunk([action_vector_to_request(vector) for vector in chunk])
            self._chunk_in_flight = False
        if not self._chunk_in_flight and self._queue.residual() <= self._rtc_params.queue_threshold:
            self._chunk_in_flight = True
            self._chunk_ready_at = self._rtc_now + latency

        if self._interpolator.residual() == 0:
            # A fresh chunk action is demanded: this is where queue exhaustion is real.
            starved = self._meter.tick(self._queue.residual())
            if starved:
                return None
            next_action = self._queue.pop()
            # pop() is non-None here: the meter reported the queue non-empty this tick.
            assert next_action is not None
            previous = self._last_published if self._last_published is not None else next_action
            self._interpolator.load(previous, next_action, self._interpolation_steps)
        request = self._interpolator.emit()
        # emit() is non-None here: the interpolator was just loaded, or still had frames.
        assert request is not None
        self._producer.publish(request)
        self._last_published = request
        return request

    def tick(self) -> RequestedPositionAction | None:
        """Dispatch one tick to the active in-process backend.

        Returns:
            (RequestedPositionAction | None) The published target, or None when a RTC
            tick was starved.

        Raises:
            BackendNotPublishableError: In `REMOTE_GRPC` mode (no mailbox target — the
                client calls `send_action()` directly) or before a backend is chosen.
        """
        if self._backend is InferenceBackend.SYNC:
            return self.sync_tick()
        if self._backend is InferenceBackend.RTC:
            return self.rtc_tick()
        raise BackendNotPublishableError(
            "the publisher does not tick in REMOTE_GRPC mode; the client calls "
            "send_action() directly (NFR-INF-008) — use remote_adapter"
        )

    def _apply_relative_action_gate(self, backend: InferenceBackend) -> None:
        """Block a relative-action policy on `sync`, forcing RTC (`FR-INF-015`, CG-4A-07d).

        Args:
            backend: The backend being switched to.

        Raises:
            InferenceParamError: If the policy is relative-action and `backend` is SYNC.
        """
        if backend is InferenceBackend.SYNC and self._policy.profile.relative_action:
            raise InferenceParamError(
                InferenceParamReason.RELATIVE_ACTION_REQUIRES_RTC,
                "a relative-action policy cannot run on the sync backend (FR-INF-015); "
                "sync is blocked and RTC is forced.",
            )

    def _param_type_error(
        self, backend: InferenceBackend, expected: str, params: BackendParams
    ) -> TypeError:
        """Build the wrong-params-type error for a backend switch.

        Returned rather than raised so the caller's `isinstance` narrowing survives.

        Args:
            backend: The backend being configured.
            expected: The parameter type name the backend requires.
            params: The supplied (wrong-typed) parameters.

        Returns:
            (TypeError) The error for the call site to raise.
        """
        return TypeError(f"{backend} requires {expected}; got {type(params).__name__}")

    def _reset_runtime(self) -> None:
        """Reset policy state and the async buffers (queue, interpolator, RTC clock)."""
        self._policy.reset()
        self._queue.clear()
        self._interpolator.reset()
        self._chunk_in_flight = False
        self._chunk_ready_at = 0.0
        self._rtc_now = 0.0
        self._last_published = None
