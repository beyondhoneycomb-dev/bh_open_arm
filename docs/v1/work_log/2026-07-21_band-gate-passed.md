# 2026-07-21 — the BOOT band acceptance gate passes

Follows `2026-07-20_band-gate-triage-and-seeder-repair.md`, which took the gate from 138
findings to 67. This session took it from 67 to **0 judged findings** — the gate is green,
`registry.check --all` exits 0, and the dashboard reads `착수 가능`.

Once this gate is green, `FAIL_BLOCKING` lifts and work packages may start (`00` §3.5).

## What the gate required, and how each cluster resolved

Band acceptance condition ② (`02a` §−2.2) is "`CI-01`..`CI-17` green on the band's own
corpus". The 67 remaining findings fell into six clusters, resolved as follows.

| cluster | n | resolution |
|---|---|---|
| CI-14 exec-class | 4 | catalogue token corrected so class derives from shape (`00` §4.0) |
| CI-14 six-element gates | 18 | doc 04 gates restructured into the six `00` §4.1 elements, from doc 03 prose |
| CI-14b shape sequence | 1 | seeder parse bug — shape cell gloss double-read; parser strips the parenthetical |
| CI-03d primitive precedence | 5 | contract-bump trigger derived from consumes (`06` §4.3), CI-03d keeps its consumes teeth |
| CI-11c provisional consumption | 3 | new `재도출 =` declaration clause; WP-1-04/05/06 declare `PG-RT-001b:PASS` |
| CI-12 target coverage | 10 | new `타깃 =` clause; the 10 `PG-IK-001` carriers declare all four targets |
| CI-04 gateless (masking) | 3 | checker fixed to count `CG-*` derivation, not `gate[]` length; WP-2A-06/2C-06 enumerated |
| CI-16 invisible edges | 3 | one phantom edge removed, two real data-joins justified |
| CI-07 normalisation hash | 22 | excluded from judging (Wave −1 circularity), plus a checker precision fix |

## Why

### The hybrid axis model — derive where a checker keeps teeth, declare where it doesn't

Three checkers (`CI-03d`, `CI-11c`, `CI-12`) judge record axes (`stale_on`, `targets`) that
the seeder never populated and the catalogue had no column to declare. The plan is split on
these: `06` §4.3 says derive them ("전 소비자 WP가 `stale_on: CTR-*:MAJOR_BUMP`"), the CI
rule texts say check them as declarations. Deriving makes the checker vacuous — the forge
pattern reverted last session; not deriving leaves the axis empty and the checker
permanently red.

The user ruled: **hybrid.** Derive only where an independent check survives:

- `CI-03d`'s contract-bump trigger *is* derived from `consumes`, faithful to `06` §4.3 — and
  `CI-03d` still bites, because its other limb judges the `consumes` axis, which is not
  derived. A Wave-3A package that fails to consume `CTR-PRIM` is still caught.
- `CI-11c`'s `PG-RT-001b:PASS` and `CI-12`'s `targets` have no independent limb, so deriving
  them would blind the checker entirely. These are **declared** — new `재도출 =` and `타깃 =`
  clauses the seeder reads. `WP-1-04`'s acceptance ⑤-b already stated the CI-11c obligation
  in prose; the clause makes it machine-readable.

The general rule this session kept proving: **a field a rule judges must come from the
declaration that rule is judging.** The moment the generator supplies it, the rule can no
longer fail.

### CI-04 was masked, and the checker's premise had quietly broken

`CI-04` (gateless work package) checked `gate[]` length. That was a correct proxy for "has
an acceptance item" *only while `gate[]` held nothing but `CG-*`*. Once last session's fix
bound `PG-*` measurement gates into `gate[]`, a package could carry a `PG-*` and still
enumerate zero acceptance items — the exact defect the rule exists to catch — and `gate[]`
would be non-empty, so the rule went silent. Per the user's ruling the checker now counts
`CG-*` derivations, restoring the rule's real premise; `WP-2A-06`/`WP-2C-06` were then
enumerated (prose deliverables numbered into `①②③`, no invented thresholds).

### CI-16 — one phantom edge, two invisible-but-real ones

`WP-BOOT-02`'s three declared downstream edges all showed no static reference. Reading the
code settled each: `BOOT-03` reads `registry/build/manifests/**` (`corpus.py`) and `BOOT-04`
reads them via `ops/launch/manifest.py` — real data joins a Python import graph cannot see,
which is exactly what `06` §5.6 describes and `06`:576 provides `justification` for. But
`BOOT-05` reads `registry/traceability.yaml` and `docs/plan` and builds its *own*
freeze-aware `contract_index`; it never touches `BOOT-02`'s output. Its input line claiming
"`WP-BOOT-02` `contract_index` 생성기" overstated the dependency, so the edge was phantom.
Corrected the input to match the code (removing the phantom edge), then declared the
justification for the two real ones.

### CI-07 is circular, the same way CI-18 is

`CI-07` requires a normalisation hash that `WP-N1-04` mints in Wave −1. Wave −1 is blocked
by this gate. So `CI-07` green → hash exists → Wave −1 ran → gate passed → Wave −1 opened:
the identical circularity `CI-18` has, which the plan resolved by excluding `CI-18` from the
judged range. The user ruled the same for `CI-07`, with one difference recorded in code and
canon: **`CI-18`'s exclusion is permanent (self-reference); `CI-07`'s is temporal.** Once
Wave −1 lands the hashes and the registry re-seeds, `CI-07` goes green on its own and should
be removed from `JUDGE_EXCLUDED`. Separately, the checker was over-harvesting — its ledger
scan read the rationale and enforcement columns, catching requirements that were the
*evidence* for a normalisation ruling, not a side of the dispute; scoped it to the contested
columns (removed one false positive, `FR-MOT-032`).

Decoupling this cleanly required splitting `check.py`'s tally-passing: it had passed the
judged-finding count to *every* excluded rule, which only worked while the set was `CI-18`
alone (whose predicate reads it). `GATE_STATE_RULES` now names just the rules that consume
the tally, so `CI-07` is called with the corpus alone.

### The dashboard held a second copy of the judge range

`dashboard/render.py` decided which rules count with its own positional `JUDGED_THROUGH`
constant — a duplicated contract that diverged the moment `CI-07` was excluded. It now
imports `JUDGE_EXCLUDED`, so the page and the checker cannot disagree about what the gate
judges.

## Verification

```bash
.venv/bin/python -m pytest -q                                   # 477 passed
.venv/bin/python -m ruff check registry ops dashboard tests     # All checks passed
.venv/bin/python -m ruff format --check registry ops dashboard tests
.venv/bin/python -m mypy registry ops dashboard                 # 80 source files
.venv/bin/python -m registry.ingest.cli --check                 # 1216 records, 177/177
.venv/bin/python -m registry.generate.cli --check               # 182 files match
.venv/bin/python -m registry.check --all                        # 0 judged findings — GREEN, exit 0
.venv/bin/python -m dashboard.render                            # 착수 가능 (pass)
```

Every finding cleared this session was independently re-verified, and every fix ran through
an adversarial audit instructed to prove a finding had been silenced rather than fixed. The
audits caught two things the implementers missed: the `CI-04` masking (a rule literally
faithful to its text, gone silent because its premise broke) and, in the prior session, the
`stale_on` forge. Both are recorded above because they are the failure mode this band is
built to prevent — a checker green while catching nothing.

## Follow-ups

1. **Lift `CI-07` from `JUDGE_EXCLUDED` after Wave −1** mints the normalisation hashes. The
   rationale and the trigger are in `registry/checks/__init__.py` and `02a` §−2.2.
2. **Seven judged rules are vacuous at landing** (`CI-03b`, `CI-04d`, `CI-05b`, `CI-05d`,
   `CI-09`, `CI-11`, `CI-13`) and contribute to the green verdict. This is honest *now* —
   the things they check (error codes, OUT records, alternative WPs, retry WPs, frozen-
   contract violations, `@target` constants, gate-state changes) do not exist at BOOT
   landing. The dashboard labels them distinctly from a rule that judged and found nothing.
   They will activate as the relevant work lands; watch that they do.
3. **`registry.ingest.cli --check` is not a drift check.** It re-derives in memory and
   validates against the schema; it never compares against the committed registry. Coupled
   to `spine_ref`, which is bound to `HEAD` rather than the spine document's own last commit,
   so a real comparison would fail on every push. The two must be decided together.
4. Corpus defects from the original seeding pass, still open — see
   `2026-07-20_boot01-registry-bootstrap.md`.
