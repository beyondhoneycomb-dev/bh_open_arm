"""PG-STOP-001 comparison for phase-1: the soft-estop WS path, and the deferred real path.

`CG-5-05f` asks that a PG-STOP-001 measurement run and be shown against `04`
NFR-MAN-002's ≤20 ms P99 target. Two distinct latencies live under that heading, and
conflating them would be a forge:

  * The **soft-estop WS path** — browser input → WS → backend `STOP_HOLD` applied
    (`NFR-GUI-005`). This is measurable synthetically here: it is the command class's
    transport delay through the single WS under load. It is what a load test can
    actually produce on this host.
  * The **authoritative PG-STOP-001** — deadman-release → CAN-stop-frame on real
    motors, correlated by the kernel clock `03` §5.7.0 demands. This needs hardware
    that does not exist here, so it is DEFERRED, and the reused
    `backend.torque_bringup.stop_latency` builder REFUSES to publish it without a
    trusted clock provenance rather than inventing one.

The 20 ms figure is `[unconfirmed]` (acceptance ⑬ of the producing WP forbids nailing
it), so this module *shows* the comparison — measured P99 beside the reference — but
renders NO pass/fail. When the soft path exceeds the reference, the report carries the
SPINE §3 branch advice (shorten the renewal period, or confirm the Cat-2 hold-frame
path) as guidance, not a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.loadtest.constants import SOFT_ESTOP_PATH_LABEL
from backend.loadtest.harness import LoadRun
from backend.loadtest.stats import percentile
from backend.torque_bringup.constants import (
    FIXTURE_ENV_VAR,
    PG_STOP_001,
    STOP_LATENCY_PERCENTILE,
    STOP_LATENCY_TARGET_MS,
)
from contracts.ws.schema import WsFrameType

SECONDS_PER_MILLISECOND = 1000.0

# The SPINE §3 branch the negative case points to (`CG-5-05f` negative branch): if the
# stop path exceeds the reference, shorten the lease renewal period or confirm the
# Cat-2 hold-frame path — never silently accept the number.
_EXCEEDS_BRANCH_ADVICE = (
    "SPINE §3 branch: shorten the lease renewal period, or confirm the Cat-2 hold-frame "
    "path — do not accept the overrun silently"
)


@dataclass(frozen=True)
class StopPathComparison:
    """The soft-estop path P99 shown against the `[unconfirmed]` 20 ms reference.

    Attributes:
        path_label: Which stop path this measured — the synthetic soft-estop WS path,
            never the authoritative release-to-CAN-stop path.
        sample_count: Frames the P99 was taken over.
        p99_ms: The measured P99 of the soft-estop path, milliseconds.
        reference_target_ms_unconfirmed: `04` NFR-MAN-002's 20 ms, carried as a
            reference only.
        exceeds_reference: Whether the measured P99 is above the reference figure.
        is_pass_fail: Always False — SPINE §2-6 forbids a pass line before the target
            is confirmed, so this comparison renders no verdict.
        note: The reference caveat, plus the SPINE §3 branch advice when exceeded.
    """

    path_label: str
    sample_count: int
    p99_ms: float
    reference_target_ms_unconfirmed: float
    exceeds_reference: bool
    is_pass_fail: bool
    note: str


def measure_soft_estop_path(run: LoadRun) -> StopPathComparison:
    """Measure the soft-estop WS path P99 under load and compare it to the reference.

    The soft-estop path is the command class's transport delay through the single WS:
    an operator's E-stop is a command frame, and its worst-case wait behind the queue
    is exactly what the load test stresses. The comparison shows the P99 beside the
    20 ms reference and renders no pass/fail.

    Args:
        run: The completed load run whose command-class latency is the soft path.

    Returns:
        (StopPathComparison) The measured P99 against the reference, no verdict.

    Raises:
        ValueError: If the command class delivered no frames — there is no soft path
            to measure, and a zero is not substituted for a missing measurement.
    """
    command = run.result(WsFrameType.COMMAND)
    if not command.latencies_sec:
        raise ValueError(
            "the command class delivered no frames; the soft-estop path P99 cannot be "
            "measured and is not reported as zero"
        )
    p99_ms = percentile(command.latencies_sec, STOP_LATENCY_PERCENTILE) * SECONDS_PER_MILLISECOND
    exceeds = p99_ms > STOP_LATENCY_TARGET_MS
    note = (
        f"soft-estop WS path only (NFR-GUI-005), NOT the authoritative release-to-CAN-stop "
        f"PG-STOP-001; {STOP_LATENCY_TARGET_MS} ms is an [unconfirmed] reference, no pass/fail "
        f"is rendered (SPINE §2-6)"
    )
    if exceeds:
        note = f"{note}. {_EXCEEDS_BRANCH_ADVICE}"
    return StopPathComparison(
        path_label=SOFT_ESTOP_PATH_LABEL,
        sample_count=len(command.latencies_sec),
        p99_ms=p99_ms,
        reference_target_ms_unconfirmed=STOP_LATENCY_TARGET_MS,
        exceeds_reference=exceeds,
        is_pass_fail=False,
        note=note,
    )


def deferred_real_stop_latency() -> dict[str, Any]:
    """Record the authoritative PG-STOP-001 as deferred, with its re-verification hook.

    The real release-to-CAN-stop latency needs real motors and the kernel clock
    `03` §5.7.0 demands; neither exists on this host. Rather than fabricate a sample or
    a clock provenance (the reused `stop_latency` builder refuses both), this records
    the gate as awaited and names the fixture env var the on-rig run will supply.

    Returns:
        (dict[str, Any]) The deferred manifest for the authoritative PG-STOP-001.
    """
    return {
        "gate": PG_STOP_001,
        "status": "deferred",
        "reason": (
            "release-to-CAN-stop needs real motors plus the 03 §5.7.0 kernel clock; "
            "unavailable on this host, and a candump-derived latency is a forge"
        ),
        "awaited_inputs": [
            "real deadman-release samples on torque-ON motors",
            "a trusted clockProvenance (kernel_evdev_so_timestamping or independent_gpio_marker)",
        ],
        "reverification_hook": "backend.torque_bringup.stop_latency.build_stop_latency_artifact",
        "fixture_env_var": FIXTURE_ENV_VAR,
    }
