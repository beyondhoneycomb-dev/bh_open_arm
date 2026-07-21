# SPINE §5 invariant → static-check map (WP-ENV-03 acceptance ① ②)

`00` §5 fixes seven global invariants (I-1…I-7). Each must be enforced by CI static
check **and** runtime assert, and each needs a violation fixture that fails CI. This
file is the map from invariant to the checker job that enforces it and the fixture
that proves the checker is not vacuous.

**Honest scope note.** Wave 0-Env lands the environment and the *plan-machine*
enforcement. The **runtime** side of I-1…I-5 (the single CAN writer, the session
lifecycle, the CAN-stream continuity, the single gateway, the holding-brake risk)
is enforced by runtime asserts and fault-injection harnesses **owned by later WPs**
(WP-0A-01 onward) — that code does not exist at this wave, so its runtime violation
fixture lands with that WP. This is recorded, not faked: no green is claimed for a
check whose subject code is not yet present. I-6 and I-7 are enforceable **now** and
carry live failing fixtures.

| # | Invariant | Static check that enforces it now | Violation fixture (fails CI) | Runtime-side status |
|---|---|---|---|---|
| **I-1** | Always-on actuation — single CAN writer, one of 4 emissions per tick | Registry encodes NORM-002 (`CONNECTED`/`SAFE_HOLD` map to an emission); `registry.check` CI-01..18 over the registry + BOOT-03 fixture corpus | `tests/boot03` false-negative corpus (registry-structural) | Runtime 0-emission/2-emission fixture **DEFERRED → WP-0A-01** (owns the fault-injection harness) |
| **I-2** | `connect()` once per session | ENV-04 fact `MAKE_ROBOT_HARDCODED_OPENARM` + `set_zero_position` on connect are the introspected upstream basis | `registry.env.cli --check` fails if the upstream fact regresses | Session-lifecycle runtime assert **DEFERRED → WP-0A / session WPs** |
| **I-3** | SW never cuts the CAN stream (except hard E-Stop) | Registry encodes NORM-006/007 (no power-cut boundary invented); CI-01..18 | BOOT-03 corpus | GUI power-cut-symbol static scan **DEFERRED → GUI WPs** (no GUI code yet) |
| **I-4** | Single gateway = `send_action()` override | ENV-04 fact `SEND_ACTION_TAU_DQ_ZERO` (the override point exists and pins dq/tau=0) | `registry.env.cli --check` fails if `send_action` stops hardcoding 0 | Gateway runtime enforcement **DEFERRED → WP-0A / gateway WP** |
| **I-5** | No holding brake = permanent physical risk (not a defect) | NORM-007 (a non-functional power-cut widget is refused, so no false safety hides the risk) | `tests/env03` plugin/config lints + BOOT-03 corpus | Physical invariant; recorded, enforced by *not* adding a fake safety |
| **I-6** | No target before measurement | `registry.check` **CI-11** — a gate carrying a frequency threshold before `PG-RT-001a` fails; it is VACUOUS now precisely because no premature threshold exists | A registry fixture placing a threshold pre-`PG-RT-001a` fails CI-11 | Enforceable now (registry-level) |
| **I-7** | Silent-failure defences (push_to_hub=false, side required, follower/leader-coupled `use_velocity_and_torque`, deg/rad/Nm) | ENV-04 facts (`USE_VEL_TORQUE_DEFAULT_FALSE`, `SIDE_REQUIRES_EXPLICIT`, `MAX_RELATIVE_TARGET_OFF`) + `.github/premerge_lint.py` | `tests/env03/test_premerge_lint.py` (push_to_hub=true → reject; bad plugin name → reject); `tests/env04` fake-config detection | **Live now** |

## What "a violation fixture fails CI" means per job

* `invariant-static` runs `registry.check --all` and `pytest tests/boot03 tests/env03`
  — the BOOT-03 false-negative corpus is the standing proof that each CI-01..18 rule
  fails on a violation (it is not vacuous).
* `contract-regress` runs `registry.env.cli --check`; `tests/env04` includes a
  fake-config whose `use_velocity_and_torque` default is `True` and asserts the
  checker **detects** it — the I-7 violation fixture.
* `pin-verify` includes the phantom-`0.6.1` spec fixture (`tests/env01`), which the
  phantom checker rejects.
