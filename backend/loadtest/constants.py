"""Named parameters of the WP-5-05 phase-1 WS load test (`13` §3.9 / SPINE §3 / U-4).

Nothing here is a *pass line*. `NFR-GUI-004` (joint-state latency p95) and
`NFR-GUI-005` (E-stop round-trip) are both marked decision-needed, and SPINE §2-6
forbids a target before the measurement exists — so this WP proves a measurement is
produced and proves the ordering invariants, and decides no threshold. The values
below are either load-generation knobs (how much synthetic traffic to make),
spec-given rates that are already confirmed elsewhere and reused here, or report
labels.

Two rates are mirrored, not owned:

  * `WS_PUBLISH_RATE_DEFAULT_HZ` / `WS_PUBLISH_RATE_MAX_HZ` are `NFR-GUI-003`'s
    confirmed 30 Hz default / 60 Hz cap. The frontend owns the runtime governor
    (`frontend/src/viewport/constants.ts` PUBLISH_RATE_DEFAULT_HZ / MAX_HZ and
    `viewport/state/publishRate.ts`). This harness runs in Python and cannot import
    a TypeScript module, so the two numbers are mirrored here for the phase-1
    governor. That mirror is a value-copy of a confirmed spec constant, not a second
    truth over a contested one, and it creates no import-graph edge (`06` §5.6).
  * `CONTROL_LOOP_POLL_RATES_HZ` are `13` §2.4's control-loop poll rates the WS must
    NOT forward at full rate. They are the reference the leak check reads.
"""

from __future__ import annotations

# `NFR-GUI-003` (`13` §2.4, confirmed): the joint-state WS publish rate is 30 Hz by
# default and 60 Hz at the cap. A request over the cap is REJECTED, not clamped —
# silently clamping would hide that the operator asked for a rate the link will not
# sustain (mirrors the frontend `resolvePublishRate` contract).
WS_PUBLISH_RATE_DEFAULT_HZ = 30.0
WS_PUBLISH_RATE_MAX_HZ = 60.0

# `13` §2.4: the control loop polls at 50 Hz or 100 Hz, and the view is decimated
# from it. "Full-rate leak" is the anti-pattern of pushing every control-loop tick
# straight onto the WS; the cap (60 Hz) sits strictly below the fast loop (100 Hz),
# so the fast loop's full rate can never resolve as a publish rate.
CONTROL_LOOP_POLL_RATES_HZ = (50.0, 100.0)

# The round-trip latency percentiles the HOL judge reports. p99 is the tail
# `NFR-GUI-012`'s H2 revision names for the load-test verdict; p50/p95 are reported
# alongside so the shape of the distribution is visible, not just its tail.
ROUNDTRIP_PERCENTILES = (50.0, 95.0, 99.0)
ROUNDTRIP_TAIL_PERCENTILE = 99.0

# `NFR-GUI-012`: a WS client is either co-located with the backend (localhost) or on
# the LAN. The two have different link budgets, so the report labels which one a run
# modelled — a localhost run that never saturates proves nothing about the LAN.
CLIENT_LOCALITY_LOCALHOST = "localhost"
CLIENT_LOCALITY_LAN = "lan"

# JPEG preview compression ratio used to size a synthetic camera *preview* frame from
# its uncompressed profile bandwidth (`NFR-GUI-012` measures the camera sum in JPEG
# bytes/s). It is a load-model parameter — how big a preview frame is on the wire —
# not a spec target or a pass line; `06` §2.9's uncompressed formula (reused via
# `backend.camera.bandwidth`) gives the raw size this divides.
JPEG_PREVIEW_COMPRESSION_RATIO = 10.0

# The verbatim residual-risk statement the report must carry (`CG-5-05e`, U-4
# original wording). A passing load test does not erase it: the soft E-stop can be
# as late as head-of-line blocking, and the only device that is not subject to HOL
# is the physical power-line button. The acceptance for item 5 asserts this exact
# string is present in the report.
RESIDUAL_RISK_STATEMENT = (
    "The browser soft E-Stop can be as late as head-of-line blocking; "
    "the real safety device is the physical power-line button (16 §4 M-2). "
    "A passing load test does not erase this line."
)

# Environment variable the phase-2 (real-camera occupancy) re-verification hook
# reads. Phase-2 is `AI-on-HW` and there is no camera on this host, so until this
# points at a real-capture directory the real-camera measurement is skipped with a
# reason — never asserted green, never faked.
PHASE2_FIXTURE_ENV_VAR = "OPENARM_LOADTEST_REAL_FIXTURE"

# The `03` §5.7 gate this WP's stop-path comparison reads. The authoritative
# release-to-CAN-stop measurement (`PG-STOP-001`) needs real motors plus the kernel
# clock `03` §5.7.0 demands; the synthetic soft-estop WS path measured here is a
# different, browser-to-backend measurement and is labelled as such.
SOFT_ESTOP_PATH_LABEL = "synthetic_ws_soft_estop"
