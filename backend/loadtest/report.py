"""Assemble the WP-5-05 phase-1 load-test report from the run and the judges.

One artifact that answers all six acceptance items on the synthetic load: the control
latency measurement (⓵ `CG-5-05a`), the camera-degrades-first ordering (② `CG-5-05b`)
with the backpressure-policy proof behind it, the 30/60 publish-rate contract (③
`CG-5-05c`), the WS-delay → lease-expiry → auto-hold mechanism (④ `CG-5-05d`), the
verbatim residual-risk statement (⑤ `CG-5-05e`), and the stop-path comparison against
the `[unconfirmed]` 20 ms reference (⑥ `CG-5-05f`) with the authoritative PG-STOP-001
recorded as deferred. Phase-2 (real-camera occupancy) is carried as a deferred status,
never a fabricated pass.

The report renders NO overall pass/fail on latency: it states the measurements exist
and the orderings hold, which is exactly what phase-1 is allowed to conclude.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.loadtest.backpressure import verify_backpressure_policy
from backend.loadtest.constants import RESIDUAL_RISK_STATEMENT
from backend.loadtest.harness import LoadRun
from backend.loadtest.hol_judge import (
    OrderingVerdict,
    judge_ordering,
    measure_roundtrip,
)
from backend.loadtest.lease_delay import (
    LEASE_EXPIRED_HOLD_LABEL,
    LEASE_EXPIRED_HOLD_REASON,
    SAFETY_LATCH_HOLD_LABEL,
    decide_when_latched,
    decide_with_expired_lease_and_fresh_target,
    inject_ws_delay,
)
from backend.loadtest.publish_rate import verify_publish_rate_policy
from backend.loadtest.reverify import reverify_phase2_from_fixture
from backend.loadtest.stop_path import deferred_real_stop_latency, measure_soft_estop_path

WP_ID = "WP-5-05"


class LoadTestReportRefusedError(Exception):
    """The load-test report was refused because an ordering invariant did not hold.

    Raised instead of publishing a green-looking report when the camera did NOT degrade
    first (`CG-5-05b` negative branch), the backpressure policy was unsound, the
    publish-rate contract broke, or the delay did not drive an auto-hold. THE ONE RULE:
    a report never fakes a green — a broken invariant is a refusal, not a footnote.
    """


@dataclass(frozen=True)
class LoadTestReport:
    """The assembled phase-1 report and whether every ordering invariant held.

    Attributes:
        artifact: The full report dictionary, one section per acceptance item.
        all_orderings_hold: Whether the ordering invariants (②③④) all held; the
            latency numbers (①⑥) are measurements and carry no pass/fail.
    """

    artifact: dict[str, Any]
    all_orderings_hold: bool


def build_load_test_report(run: LoadRun) -> LoadTestReport:
    """Assemble the phase-1 load-test report, refusing it if an ordering invariant fails.

    Args:
        run: The completed synthetic load run at max load.

    Returns:
        (LoadTestReport) The report artifact and the ordering summary.

    Raises:
        LoadTestReportRefusedError: If the camera did not degrade first, the
            backpressure policy is unsound, the publish-rate contract broke, or the
            injected delay did not drive an auto-hold.
    """
    roundtrip = measure_roundtrip(run)
    ordering = judge_ordering(run)
    backpressure = verify_backpressure_policy()
    publish_rate = verify_publish_rate_policy()
    lease_delay = inject_ws_delay()
    stop_path = measure_soft_estop_path(run)
    phase2 = reverify_phase2_from_fixture()

    expired_hold = decide_with_expired_lease_and_fresh_target()
    latched_hold = decide_when_latched()

    ordering_holds = (
        ordering.verdict is OrderingVerdict.PROTECTED
        and backpressure.sound
        and publish_rate.holds
        and lease_delay.latched
    )

    artifact: dict[str, Any] = {
        "wp_id": WP_ID,
        "phase": 1,
        "renders_pass_fail_on_latency": False,
        "link": {
            "locality": run.profile.locality,
            "saturating": run.profile.is_saturating(),
            "peak_buffered_bytes": run.peak_buffered_bytes,
            "camera_preview_bytes_per_sec": run.profile.camera_preview_bytes_per_sec(),
            "link_capacity_bytes_per_sec": run.profile.link_capacity_bytes_per_sec,
            "client_count": run.profile.client_count,
        },
        # ① CG-5-05a — the measurement exists; no threshold applied.
        "cg_5_05a_roundtrip": {
            "note": roundtrip.no_threshold_note,
            "classes": {
                frame_type.value: {
                    "sample_count": profile.sample_count,
                    "percentiles_sec": {
                        str(pct): sec for pct, sec in profile.percentiles_sec.items()
                    },
                }
                for frame_type, profile in roundtrip.profiles.items()
            },
        },
        # ② CG-5-05b — camera degrades first; backpressure policy proven behind it.
        "cg_5_05b_ordering": {
            "verdict": ordering.verdict.value,
            "camera_dropped": ordering.camera_dropped,
            "protected_dropped": ordering.protected_dropped,
            "reason": ordering.reason,
            "backpressure_policy": {
                "sound": backpressure.sound,
                "camera_shed_over_threshold": backpressure.camera_shed_over_threshold,
                "camera_kept_under_threshold": backpressure.camera_kept_under_threshold,
                "protected_never_shed": backpressure.protected_never_shed,
                "violations": list(backpressure.violations),
            },
        },
        # ③ CG-5-05c — 30 default / 60 cap; no control-loop full-rate leak.
        "cg_5_05c_publish_rate": {
            "default_hz": publish_rate.default_hz,
            "cap_hz": publish_rate.cap_hz,
            "over_cap_rejected": publish_rate.over_cap_rejected,
            "fast_loop_full_rate_rejected": publish_rate.fast_loop_full_rate_rejected,
            "default_decimates_all_loops": publish_rate.default_decimates_all_loops,
            "holds": publish_rate.holds,
            "violations": list(publish_rate.violations),
        },
        # ④ CG-5-05d — WS delay → lease expiry → scheduler auto-hold.
        "cg_5_05d_lease_autohold": {
            "latched": lease_delay.latched,
            "seconds_from_last_renewal_to_hold": lease_delay.seconds_from_last_renewal_to_hold,
            "lease_duration_sec": lease_delay.lease_duration_sec,
            "expired_with_fresh_target_emission": {
                "label": expired_hold.label.value,
                "reason": expired_hold.reason.value,
                "is_expected_lease_hold": (
                    expired_hold.label is LEASE_EXPIRED_HOLD_LABEL
                    and expired_hold.reason is LEASE_EXPIRED_HOLD_REASON
                ),
            },
            "latched_emission": {
                "label": latched_hold.label.value,
                "is_expected_safety_hold": latched_hold.label is SAFETY_LATCH_HOLD_LABEL,
            },
        },
        # ⑤ CG-5-05e — the residual risk, verbatim.
        "cg_5_05e_residual_risk": RESIDUAL_RISK_STATEMENT,
        # ⑥ CG-5-05f — soft-estop path vs the [unconfirmed] 20 ms reference; real deferred.
        "cg_5_05f_stop_path": {
            "soft_estop": {
                "path_label": stop_path.path_label,
                "sample_count": stop_path.sample_count,
                "p99_ms": stop_path.p99_ms,
                "reference_target_ms_unconfirmed": stop_path.reference_target_ms_unconfirmed,
                "exceeds_reference": stop_path.exceeds_reference,
                "is_pass_fail": stop_path.is_pass_fail,
                "note": stop_path.note,
            },
            "authoritative_pg_stop_001": deferred_real_stop_latency(),
        },
        "phase2_real_camera_occupancy": {
            "ran": phase2.ran,
            "reason": phase2.reason,
            "fixture_env_var": phase2.fixture_env_var,
        },
    }

    if not ordering_holds:
        raise LoadTestReportRefusedError(
            "refusing to publish the WP-5-05 report: an ordering invariant did not hold — "
            f"ordering={ordering.verdict.value}, backpressure_sound={backpressure.sound}, "
            f"publish_rate_holds={publish_rate.holds}, lease_autohold={lease_delay.latched}"
        )

    return LoadTestReport(artifact=artifact, all_orderings_hold=ordering_holds)
