"""Assemble the WP-1-04 evidence artifact and refuse it when a precondition fails.

This is where the offline part of WP-1-04 comes together. It reuses the `WP-0C-06`
synthetic artifact for the full histograms, the seven conditions, the GIL contribution
and the RT-promotion gain (acceptance ①⑥⑦⑪ — those all run here on the synthetic
load), and adds this WP's own judgments on top: the `PG-RT-001a` verdict over the
sweep (⑤), the `PG-CAN-001` frame verdict (⑧), the `f_max` figure (⑨), the
synthetic-vs-real comparison table (⑥), the provisional `f_max_python` with its
re-derivation trigger (⑤-b), and the target-host record (⑩).

Four refusals bite here, as hard errors, because `THE ONE RULE` is that a run never
fakes an acceptance:

  * ②③④ The measurement session must have connected exactly once, still hold the
    channel lock, and read torque-OFF; otherwise the artifact is not published.
  * ⑤-b The artifact must declare `PG-RT-001b:PASS` in its `stale_on`, or the
    provisional synthetic figure could survive as final (`06` CI-11c).

The real-CAN inputs — `f_max_can`, the real `candump` count, the real condition-4
distribution — are deferred and default to absent; the artifact records them as
awaited rather than inventing them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.can.lock.connect_guard import LockOrderingError
from backend.rtbench.constants import (
    PROVISIONAL_GATE,
    REQUIRED_STALE_TRIGGER,
    SYNTHETIC_BASIS,
)
from backend.rtbench.fmax import FMax, compute_fmax
from backend.rtbench.frame_count import (
    FrameCountSource,
    PgCan001Verdict,
    judge_pg_can_001,
)
from backend.rtbench.judge import (
    BandPoint,
    PgRt001aVerdict,
    band_points_from_sweep,
    judge_pg_rt_001a,
)
from backend.rtbench.session import (
    NotConnectedError,
    ReadOnlyMeasurementSession,
    RepeatedConnectError,
    TorqueEngagedError,
)
from sim.harness.artifact import build_artifact
from sim.harness.harness import HarnessResult

WP_ID = "WP-1-04"


class MeasurementArtifactRefusedError(Exception):
    """The WP-1-04 measurement artifact was refused publication.

    Raised instead of writing a defective artifact, so a run that lost its lock, ran
    torque-on, connected the wrong number of times, or would publish a provisional
    figure without its re-derivation trigger fails loudly rather than emitting a
    green-looking result.
    """


def _assert_session_publishable(session: ReadOnlyMeasurementSession[Any]) -> None:
    """Re-raise the session's precondition failures as a single refusal (②③④).

    Args:
        session: The measurement session.

    Raises:
        MeasurementArtifactRefusedError: If the session is not in a publishable state.
    """
    try:
        session.assert_publishable()
    except (
        NotConnectedError,
        RepeatedConnectError,
        LockOrderingError,
        TorqueEngagedError,
    ) as cause:
        raise MeasurementArtifactRefusedError(
            f"refusing to publish the WP-1-04 artifact: {cause}"
        ) from cause


def _condition4_band_point(result: HarnessResult) -> BandPoint:
    """Build the band point for condition 4's own operating frequency.

    The sweep covers the band, but condition 4 is measured at the harness's base
    target frequency; including it keeps the operating point itself in the judged set.

    Args:
        result: The completed harness run.

    Returns:
        (BandPoint) Condition 4's frequency and its overrun rate.
    """
    condition4 = result.condition(4)
    period = condition4.period_sec
    if condition4.histogram is None or period is None:
        raise MeasurementArtifactRefusedError(
            "condition 4 carries no timing distribution; cannot judge PG-RT-001a"
        )
    overrun = condition4.histogram.overrun_rate(period, result.config.overrun_tolerance)
    return BandPoint(target_hz=result.config.target_hz, overrun_rate=overrun)


def _judged_band(result: HarnessResult) -> tuple[BandPoint, ...]:
    """Assemble the full judged band: the sweep points plus condition 4's point.

    Args:
        result: The completed harness run.

    Returns:
        (tuple[BandPoint, ...]) Every band point PG-RT-001a is judged over.
    """
    return band_points_from_sweep(result.fmax_sweep) + (_condition4_band_point(result),)


def _synthetic_frame_verdict(result: HarnessResult) -> PgCan001Verdict:
    """Judge the modelled frames-per-cycle from condition 7 as provisional.

    Args:
        result: The completed harness run.

    Returns:
        (PgCan001Verdict) The provisional frame verdict from the synthetic model.
    """
    modelled = int(result.condition(7).extra["frames_per_cycle_model"])
    return judge_pg_can_001(modelled, FrameCountSource.SYNTHETIC_MODEL)


def _comparison_table(
    result: HarnessResult, real_condition4: dict[str, Any] | None
) -> dict[str, Any]:
    """Build the synthetic-vs-real condition-4 comparison table (acceptance ⑥).

    The synthetic side runs here; the real side is filled by `PG-RT-001b` on the rig.
    Until then the real column is null and the delta is undefined, recorded plainly so
    a reviewer knows what is still awaited — this table is the only basis for saying
    what was wrong when `b` overturns `a`.

    Args:
        result: The completed harness run.
        real_condition4: The real condition-4 distribution summary, or None when
            deferred.

    Returns:
        (dict[str, Any]) The comparison table with its synthetic and (deferred) real
        columns.
    """
    condition4 = result.condition(4)
    synthetic = condition4.histogram.summary() if condition4.histogram is not None else None
    return {
        "metric": "condition_4_cycle_time",
        "synthetic": synthetic,
        "real": real_condition4,
        "real_source": "PG-RT-001b (WP-3C-02) real cameras + real writer",
        "delta": None if real_condition4 is None else _summary_delta(synthetic, real_condition4),
        "note": (
            "synthetic side measured here; real side deferred to PG-RT-001b — the delta "
            "is the only basis for saying what was wrong when b overturns a"
        ),
    }


def _summary_delta(
    synthetic: dict[str, float] | None, real: dict[str, Any]
) -> dict[str, float] | None:
    """Compute per-key deltas between two distribution summaries.

    Args:
        synthetic: The synthetic summary.
        real: The real summary.

    Returns:
        (dict[str, float] | None) real minus synthetic per shared key, or None when the
        synthetic side is absent.
    """
    if synthetic is None:
        return None
    shared = set(synthetic) & set(real)
    return {key: float(real[key]) - float(synthetic[key]) for key in sorted(shared)}


def _provisional_fmax_python(fmax: FMax) -> dict[str, Any]:
    """Publish `f_max_python` as provisional with its re-derivation trigger (⑤-b).

    Args:
        fmax: The combined `f_max` figure.

    Returns:
        (dict[str, Any]) The provisional figure, flagged non-verdict and carrying the
        `PG-RT-001b:PASS` staleness trigger that stops it surviving as final.
    """
    return {
        "value_hz": fmax.f_max_python_hz,
        "provisional": True,
        "is_verdict": False,
        "basis": SYNTHETIC_BASIS,
        "stale_on": [REQUIRED_STALE_TRIGGER],
        "note": (
            "provisional synthetic estimate; PG-RT-001b (WP-3C-02) is the canonical "
            "gate and can supersede it (06 CI-11c)"
        ),
    }


def _assert_provisional_marked(artifact: dict[str, Any]) -> None:
    """Refuse the artifact unless it declares the `PG-RT-001b:PASS` trigger (⑤-b).

    Args:
        artifact: The assembled artifact.

    Raises:
        MeasurementArtifactRefusedError: If the re-derivation trigger is absent.
    """
    if REQUIRED_STALE_TRIGGER not in artifact.get("stale_on", []):
        raise MeasurementArtifactRefusedError(
            f"artifact does not declare {REQUIRED_STALE_TRIGGER} in stale_on; a provisional "
            "synthetic figure would survive as final (06 CI-11c, acceptance ⑤-b)"
        )


def build_measurement_artifact(
    *,
    session: ReadOnlyMeasurementSession[Any],
    harness_result: HarnessResult,
    host_id: str,
    is_fleet_target: bool,
    f_max_can_hz: float | None = None,
    real_frames_per_cycle: int | None = None,
    real_condition4: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the WP-1-04 evidence artifact, refusing it if a precondition fails.

    Args:
        session: The read-only measurement session; must be publishable (②③④).
        harness_result: The completed `WP-0C-06` synthetic-load run (the `a` basis).
        host_id: The control host the measurement ran on (`05` NFR-TEL-004).
        is_fleet_target: Whether `host_id` is a real deployment target; an x86 dev host
            is not, and its numbers are recorded as not-a-fleet-verdict (⑩).
        f_max_can_hz: The `WP-0B-06` CAN-bound maximum, or None when deferred.
        real_frames_per_cycle: A real `candump` frame count, or None when deferred; when
            present it is judged as `REAL_CANDUMP` alongside the synthetic model.
        real_condition4: The real condition-4 distribution summary, or None when
            deferred.

    Returns:
        (dict[str, Any]) The full artifact: the synthetic run's histograms and derived
        metrics, this WP's verdicts, the `f_max` figure, the comparison table, and the
        provisional figure with its re-derivation trigger.

    Raises:
        MeasurementArtifactRefusedError: If the session is not publishable (②③④) or the
            provisional trigger is absent (⑤-b).
        ArtifactRefusedError: If the underlying synthetic artifact is itself defective
            (`WP-0C-06` acceptance ②⑥).
    """
    _assert_session_publishable(session)

    synthetic_artifact = build_artifact(harness_result)

    verdict: PgRt001aVerdict = judge_pg_rt_001a(_judged_band(harness_result))
    fmax = compute_fmax(f_max_can_hz, harness_result.fmax_python_provisional.get("value_hz"))

    frame_verdicts = [_synthetic_frame_verdict(harness_result).as_record()]
    if real_frames_per_cycle is not None:
        frame_verdicts.append(
            judge_pg_can_001(real_frames_per_cycle, FrameCountSource.REAL_CANDUMP).as_record()
        )

    artifact: dict[str, Any] = {
        "wp_id": WP_ID,
        "gate": PROVISIONAL_GATE,
        "gate_status": "provisional",
        "generated_at": datetime.now(UTC).isoformat(),
        "stale_on": [REQUIRED_STALE_TRIGGER],
        "target_host": {
            "host_id": host_id,
            "is_fleet_target": is_fleet_target,
            "note": (
                "x86 dev-host numbers are not a fleet verdict; re-measure on a target "
                "control host (05 NFR-TEL-004)"
            ),
        },
        "session": {
            "connect_call_count": session.connect_call_count,
            "ifaces": list(session.ifaces),
            "torque_off": True,
        },
        "pg_rt_001a": verdict.as_record(),
        "pg_can_001": frame_verdicts,
        "f_max": fmax.as_record(),
        "f_max_python_provisional": _provisional_fmax_python(fmax),
        "comparison_table": _comparison_table(harness_result, real_condition4),
        "synthetic_run": synthetic_artifact,
        "deferred": _deferred_manifest(f_max_can_hz, real_frames_per_cycle, real_condition4),
    }

    _assert_provisional_marked(artifact)
    return artifact


def _deferred_manifest(
    f_max_can_hz: float | None,
    real_frames_per_cycle: int | None,
    real_condition4: dict[str, Any] | None,
) -> dict[str, Any]:
    """Record which real-CAN inputs are still awaited and how to supply them.

    Args:
        f_max_can_hz: The CAN-bound maximum, or None when deferred.
        real_frames_per_cycle: A real `candump` count, or None when deferred.
        real_condition4: The real condition-4 summary, or None when deferred.

    Returns:
        (dict[str, Any]) The awaited inputs and the re-verification hook that consumes
        them, so the deferral is visible in the artifact rather than silent.
    """
    awaited: list[str] = []
    if f_max_can_hz is None:
        awaited.append("f_max_can (WP-0B-06 real bus)")
    if real_frames_per_cycle is None:
        awaited.append("real candump frames-per-cycle (PG-CAN-001 binding verdict)")
    if real_condition4 is None:
        awaited.append("real condition-4 distribution (PG-RT-001b)")
    return {
        "awaited_inputs": awaited,
        "reverification_hook": "backend.rtbench.reverify.reverify_from_fixture",
        "fixture_env_var": "OPENARM_RTBENCH_REAL_FIXTURE",
    }
