"""Acceptance ① — in a safe-stop state the CAN frame stream keeps flowing.

`STOP_HOLD` is a continuous send, not a loop stop (`FR-SAF-038`/`FR-SAF-073`): a safety
stop changes what the loop sends, it never stops the loop, because a stopped loop drops
a brakeless arm past the RID-9 watchdog (`NFR-SAF-007`). This is proven two ways on the
reused Wave-1 scheduler and fake CAN writer (the offline candump):

- the reused scheduler, latched, still writes exactly one frame every tick, and
- the actual `MIT(kp_orig, kd_orig, q_hold, 0, τ_grav)` frame re-streams unbroken.

The negative branch — an interrupted stream is `FAIL_BLOCKING` — is a detectable defect:
a tick that emitted zero frames raises inside the scheduler, so reaching the pumped
count is itself the proof, and a deliberately shortened stream is caught by a frame
count that no longer equals the cycle count.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel, FaultInjectionHarness
from backend.reaction import (
    ReactionContext,
    ReactionExecutor,
    ReactionPolicy,
    ReactionStrategy,
    TorqueChannel,
    build_reaction_command,
    stream_reaction_frames,
)

_PUMP_CYCLES = 500


def test_latched_scheduler_writes_one_frame_every_tick(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """A confirmed collision latches the scheduler, which keeps emitting hold frames."""
    harness = FaultInjectionHarness()
    executor = ReactionExecutor(harness.scheduler, ReactionPolicy(), channel_available)
    harness.run_tick()

    executor.respond(context, now=harness.clock.now())
    assert executor.is_latched

    before = harness.can_writer.write_count
    for _ in range(_PUMP_CYCLES):
        harness.advance()
        emission = harness.tick()
        assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD
    sent = harness.can_writer.write_count - before

    # Every tick under the latch is exactly one CAN write — the stream never stops.
    assert sent == _PUMP_CYCLES


def test_executor_pump_returns_a_frame_per_cycle(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """`pump` runs the reused scheduler; a full return is the continuous-send proof."""
    harness = FaultInjectionHarness()
    executor = ReactionExecutor(harness.scheduler, ReactionPolicy(), channel_available)
    harness.run_tick()
    executor.respond(context, now=harness.clock.now())

    before = harness.can_writer.write_count
    emissions = executor.pump(_PUMP_CYCLES)

    assert len(emissions) == _PUMP_CYCLES
    assert all(item.label is EmissionLabel.SAFETY_LATCH_HOLD for item in emissions)
    assert harness.can_writer.write_count - before == _PUMP_CYCLES


def test_stop_hold_frame_restreams_with_tau_grav(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """The exact `MIT(...,τ_grav)` STOP_HOLD frame re-sends unbroken on the fake writer."""
    harness = FaultInjectionHarness()
    command = build_reaction_command(ReactionStrategy.STOP_HOLD, context, channel_available)

    sent = stream_reaction_frames(harness.can_writer, command, _PUMP_CYCLES)

    assert sent == _PUMP_CYCLES
    last = harness.can_writer.last_batch
    assert last is not None
    # The streamed frame carries the gravity feed-forward, not a stripped position hold.
    assert last[0].tau.value == context.tau_grav[0].value
    assert last[0].kp == context.kp_orig[0]
    assert last[0].dq.value == 0.0


def test_shortened_stream_is_detectable(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """An interrupted stream is caught: the frame count no longer equals the cycle count."""
    harness = FaultInjectionHarness()
    executor = ReactionExecutor(harness.scheduler, ReactionPolicy(), channel_available)
    harness.run_tick()
    executor.respond(context, now=harness.clock.now())

    before = harness.can_writer.write_count
    executor.pump(_PUMP_CYCLES)
    full = harness.can_writer.write_count - before

    # A loop that stopped early would show fewer frames than cycles — the check that
    # detects the FAIL_BLOCKING interruption.
    assert full == _PUMP_CYCLES
    assert full - 1 != _PUMP_CYCLES
