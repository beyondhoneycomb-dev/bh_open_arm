# MJCF v2 asset audit — WP-0C-03

The repo-owned single source of truth for the OpenArm bimanual sim asset. The
files under `v2/` are vendored from the installed `openarm_mujoco` package
(`openarm_mujoco.v2.openarm_bimanual_xml()` and the sibling `cell.xml` + `assets/`
mesh tree) and then corrected. Downstream sim work (WP-0C-01/02/04/09 and the
Wave 2B friction identification) loads this copy, not the upstream buggy asset.

## 1. J7 motor-class fix

`v2/openarm_bimanual.xml` declared wrist joint 7 with `class="motor_DM3507"` on
both arms, while the same file's joint-7 actuators use `class="position_DM4310"`.
Four upstream sources — BoM, driver, teleop config, and the LeRobot registration
— agree that J7 is a **DM4310**, so the MJCF joint class was the typo.

| Site | Before | After |
|---|---|---|
| `v2/openarm_bimanual.xml:225` `openarm_left_joint7` | `class="motor_DM3507"` | `class="motor_DM4310"` |
| `v2/openarm_bimanual.xml:313` `openarm_right_joint7` | `class="motor_DM3507"` | `class="motor_DM4310"` |

Only the two joint references were changed. The `<default class="motor_DM3507">`
definition (line 34) and `<default class="position_DM3507">` (line 55) are left in
place; the acceptance criterion is **zero references**, not deletion of the
definition, and a live grep confirms `motor_DM3507` now appears only at its
`<default>` definition.

After the fix, J7 resolves through `motor_DM4310` to the same dynamics as J5/J6:

- frictionloss **0.04**, damping **0.9**, armature **0.0100**, forcerange **±7**.

Before the fix J7 resolved to the DM3507 typo triple frictionloss 0.01 / damping
0.01 / armature **0.0049**. That armature is ~2× off; because tMax and the
inertia terms feed the friction/gravity identification, a J7 domain-randomization
centre taken from the unfixed asset would carry the error into every identified
value. The DR centre source must be this fixed asset (invariant checker enforces
that `0.0049` never resolves for J7).

## 2. J2 shoulder limits (v2)

v2 shifted joint 2 by +π/2 relative to v1. The vendored asset carries the v2
limits and no v1 remnant:

- `openarm_right_joint2` range = **(−0.17453, 3.3161)**
- `openarm_left_joint2` range = **(−3.3161, 0.17453)** (mirror)
- No joint retains the v1 shoulder range **±1.745329**.

This matters beyond the sim: `mink.ConfigurationLimit` reads the MJCF `jnt_range`
as the effective IK limit source (WP-0C-02), so a v1 remnant here would corrupt
real command generation, not just visualization.

## 3. `friction.yaml` — 0 bytes (void v1 friction)

Spec `16` §10.2 records `friction.yaml` as a **0-byte file**: the v1 friction
values are void. A search of the installed asset trees
(`openarm_mujoco`, `openarm_control`) finds **no `friction.yaml` at all** — it is
not shipped in the pip package; the 0-byte file lives in the upstream source
repo. Either way the fact is the same and is the audit record here: **there are no
valid friction values in the v2 asset set.** Real friction values are the product
of Wave 2B friction identification (`PG-FRIC-001`), which is gated on `PG-J7-001`
— i.e. it cannot start until the J7 motor type is confirmed and this asset is
fixed. This is why path A (gravity/friction compensation) has not started.

## 4. Head stereo camera re-parenting

`v2/cell.xml` (the runtime scene) places `camera_head_left` and
`camera_head_right` as direct children of `<worldbody>`, immediately below the
comment `need to adjust x after lifter link is adjusted`. The head is mounted on
the lifter; parented to the world the cameras stay fixed while the arms rise, so
at any lifter stroke z ≠ 0 the simulated head viewpoint diverges from the real one
(`09` FR-SIM-006).

`v2/cell_head_reparented.xml` is the re-parented variant: the two head cameras are
children of `openarm_lifter_link`, expressed in the lifter body frame. At lifter
home (stroke 0) their world pose is byte-for-byte the same as upstream
(0.223, ∓0.0315, 1.45); the fix is that the pose now tracks the stroke. The
invariant checker treats a non-re-parented scene as a **warning**, not a hard
failure — both scenes are legitimate assets a caller may load — while asserting
that the variant does hang the cameras under the lifter.

## 5. Invariant checker

`invariant.py` audits the asset by parsing the XML directly (never through the
MuJoCo compiler, which would resolve away the very contradiction being checked):

- **Motor-class consistency** — every actuated joint's motor family (from its
  joint `class`) equals its actuator's (from the actuator `class`). The gripper
  (`motor_finger` joint dynamics driven by `position_DM4310` gains) is the one
  sanctioned divergence and is reported as a named `KNOWN_DIVERGENCE`, never
  folded silently into the pass set — so the J7 typo, which has the same
  cross-family shape, still lands in the `VIOLATION` bucket. Run against the
  unfixed upstream asset the checker reports the J7 contradiction on both arms;
  run against the fixed asset it reports zero violations.
- **J7 references** — joint 7 is `motor_DM4310` on both arms and nothing
  references `motor_DM3507`.
- **J7 DR source** — J7's resolved dynamics are the DM4310 centre, never the typo
  triple.
- **J2 limits** — v2 magnitudes, no v1 remnant.
- **Head-camera parenting** — cameras under `openarm_lifter_link` in the variant;
  warning otherwise.

## 6. MuJoCo verification (facts)

- `v2/openarm_bimanual.xml` compiles: nq/nv/nu = 18/18/16.
- `v2/cell.xml` and `v2/cell_head_reparented.xml` compile: nq/nv/nu = 19/19/17
  (lifter + 2×(7 arm + 2 finger)).
- Loaded J7 dynamics on both arms = frictionloss 0.04 / damping 0.9 / armature
  0.01, forcerange ±7 — identical to J5/J6.
