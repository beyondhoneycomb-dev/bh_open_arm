# 2026-07-20 — Band-gate triage: 138 → 67, and why the seeder was the root cause

Follows `2026-07-20_boot-band-parallel-implementation.md`, which landed `WP-BOOT-02`..`05`
and left the band acceptance gate closed with 138 findings.

## Context

Condition ② of the band gate (`02a` §−2.2) requires `CI-01`..`CI-17` green on their own
corpus. 138 findings across 10 rules stood in the way, and `FAIL_BLOCKING` means no work
package may start — Wave −1 included.

Every finding was triaged before anything was changed: one investigator per rule cluster,
each followed by a verifier instructed to refute rather than confirm. Three verdicts were
refuted, and two of those refutations changed what got built. Implementation then ran in
two workflows, each ending in an adversarial audit of its own diff.

## Files changed

- `registry/ingest/catalog.py`, `spec.py` — `REQ_ID` terminator; the pattern was
  duplicated verbatim in both modules and is now defined once.
- `registry/ingest/resolve.py` — `06` §6 range expansion.
- `registry/ingest/build.py` — gate axis read from `03` binding rows instead of scraped
  from prose; two derived-field seeders removed.
- `registry/checks/ci_11.py`, `fixtures/cases.py` — declaration granularity, and a
  vacuity note that distinguishes its two causes.
- `registry/check.py` — the check report is persisted where the dashboard reads it.
- `dashboard/render.py` — reads the report shape the producer actually emits.
- `docs/plan/02a` — five `소유 경로` clauses extended; two SPINE citations resolved.
- `docs/plan/01` — two shape citations corrected against the catalogue.
- `docs/plan/06` — §3.3 glob map rows.
- `.github/workflows/ci.yml` — the band-gate step, and `dashboard/` added to lint/types.
- `tests/boot03/` — two new files; the entry-point exit-code test made hermetic.

## Why

### One module produced 62 of the 138 findings

`CI-07` (22), `CI-11c` (35) and `CI-03d` (5) had three different rule texts, three
different checkers, and one root cause: `registry/ingest/`. The failures share a
signature, and it is the same signature as the four defects found in the previous session
— **a regex under-matches, returns fewer results, and never raises.** The registry
validates and is wrong.

**`REQ_ID` could not see an id followed by a Korean particle.** The pattern ended in
`\b`, and Hangul syllables are word characters, so `FR-GUI-060의` matched nothing at all.
Across the corpus this lost 30 id occurrences in `docs/plan` and 106 in `docs/spec`.

**`06` §6 range expressions were read as a single id.** `06`:645 assigns
`FR-GUI-060`~`074` to `WP-G-03` and `:646` assigns `FR-GUI-080`~`091` to `WP-G-04`. Only
the first literal id resolved. The remainder fell through to the weaker `sole-citation`
rule and landed on packages that merely cited them — `FR-GUI-063`/`067` on `WP-N1-02`,
`065` on `WP-G-S04` — contradicting the canon that names their owner outright. This is
"a mention is not a declaration" for the third time, this time inside the seeder rather
than the checkers.

**The gate axis was fabricated.** `_gates_for` collected every `PG-*` id appearing
anywhere in a package's acceptance cell. Two of those "gates" were sentences *about* gate
vocabulary: `WP-BOOT-01`'s acceptance ⑤ says only `PG-RT-001a`/`b` are permitted as
values, and `WP-0A-01`'s ⑨ says targets are not fixed yet *because* it precedes
`PG-RT-001a`. Both were read as declarations. Their downstream closure was 40 packages,
and all 35 `CI-11c` findings derived from it. The axis is now read from `03`'s per-gate
binding rows, which is where the corpus declares it.

### Fixing the seeder made the corpus look worse, which is the point

`CI-07` went 22 → 23, `CI-12` went vacuous → 10, `CI-14` went 9 → 22. The original 138
was an undercount: bad gate data was suppressing sites in two rules that had nothing to
do with the bug. A fix whose only effect is a smaller number is the one to distrust.

### Two fixes were reverted for satisfying the rule instead of the corpus

The first implementation pass made `stale_on` a derived field — `PG-RT-001b:PASS`
injected wherever `PG-RT-001a` appeared, and `CTR-*:MAJOR_BUMP` joined from `consumes`.
Both are defensible as software design; the comment argued, correctly in general, that
two independently maintained lists are how they drift apart.

They are wrong here. `CI-03d` and `CI-11c` exist to detect that a package **failed to
declare** a trigger it owes. A seeder that supplies the trigger satisfies both rules by
construction, and neither can fail again. The registry is the artifact under test, so a
field a rule judges has to come from the declaration that rule is judging. Reverting them
returned 8 real findings and moved the honest total from 114 to 122.

`CI-11c`'s legitimate reduction survives that revert: 35 → 3. Thirty-two of the original
findings really were derived from fabricated gates.

### `CI-02b`: ownership was declared, not excused

All 54 findings were real files no package was accountable for — 40 test files, 7 in
`registry/ingest/`, 3 in `dashboard/`, and the project skeleton. The checker is a verbatim
implementation of `06`:537 and was left untouched.

The declaration site required checking rather than assuming. `06` §3.3 does not feed the
ownership axis — `build.py`:110-114 reads only §3.2, deliberately, because §3.3 assigns
globs to a *band* and expanding those onto every package in it would manufacture `CI-02`
overlap conflicts. But §3.2 is the six-symbol fan-out prohibition list, not a general map
either. The real site is each package's inline `소유 경로` clause in its own catalogue row,
and that is where the twelve new globs went. `CI-02` (duplicate ownership) is green before
and after; falsifiability was re-proved by dropping an unowned file in and watching the
rule catch it.

### Three backstops existed and none of them enforced anything

- **`.github/workflows/ci.yml`:60 ran `--through CI-17`, which is not a flag.** Exit 2,
  `unrecognized arguments`. The BOOT band acceptance gate step has never executed. The
  judge range it was trying to express is already encoded as `JUDGE_EXCLUDED` in
  `registry/checks/__init__.py`:96, so `--all` expresses it exactly.
- **`dashboard/render.py`:27 read `registry/build/check-report.json`, which nothing
  wrote** — the only mention of that path in the repo was the line reading it. The
  verdict was permanently `판정 보류 / 미확인`, including after a genuine pass. It was two
  defects, not one: the reader also parsed a shape (`results`, `ci_id`, `violations`) that
  `as_report()` has never emitted, so persisting the file alone would have changed nothing.
- **`registry.ingest.cli --check` does not compare against the committed registry.** It
  re-derives the document in memory and validates it against the schema. `ci.yml`:49 and
  `docs/guide/01` both describe it as a drift check. It is not one. Left unfixed — see
  follow-ups, because it is coupled to a decision.

## Verification

```bash
.venv/bin/python -m pytest -q                                   # 475 passed
.venv/bin/python -m ruff check registry ops dashboard tests     # All checks passed
.venv/bin/python -m ruff format --check registry ops dashboard tests  # 122 formatted
.venv/bin/python -m mypy registry ops dashboard                 # 80 source files
.venv/bin/python -m registry.ingest.cli --check                 # 1216 records, 177/177
.venv/bin/python -m registry.generate.cli --check               # 182 files match
.venv/bin/python -m registry.check --all                        # 67 findings, exit 1
.venv/bin/python -m dashboard.render                            # 착수 불가 (fail)
```

Findings by rule: `CI-03d` 5, `CI-07` 23, `CI-11c` 3, `CI-12` 10, `CI-14` 22, `CI-14b` 1,
`CI-16` 3.

Independently re-verified rather than taken from agent reports:

- Both reverted seeder injections reproduced against `build.py` before removal, and the
  8 findings they had been suppressing confirmed to return.
- `REQ_ID`'s particle failure reproduced directly (`findall('FR-GUI-060의 …') == []`), and
  the corpus-wide delta measured against a corrected terminator.
- `06`:645's range and `resolve.py`'s lack of expansion confirmed by reading both.
- `CI-04`'s masking confirmed by querying the registry: `WP-2A-06` and `WP-2C-06` still
  derive zero `CG-*` ids.
- The CI band-gate step's exit 2 reproduced by running its exact command line.

## Follow-ups

1. **`CI-04` is masked and its underlying defect is now invisible.** The rule is a proxy:
   `06` §2.4a derives one `CG-*` per numbered acceptance item, so an empty `gate[]` meant
   a row that enumerated none. `WP-2A-06` and `WP-2C-06` still enumerate none — their
   acceptance is prose — but the `03` binding read gave them a `PG-*`, so `gate[]` is
   non-empty and the rule stopped firing. The checker is literally faithful to `06`:542;
   the signal is gone anyway. Needs a ruling: enumerate the prose in `02a`/`02c`, or make
   `CI-04` judge `CG-*` derivation rather than `gate[]` length.
2. **A vacuous judged rule currently counts toward the gate.** `model.py`:157 sets
   `passed = not findings`, so the seven vacuous judged rules (`CI-03b`, `CI-04d`,
   `CI-05b`, `CI-05d`, `CI-09`, `CI-11`, `CI-13`) will contribute green once the seven
   failing ones are fixed. `02a` §−2.3's worst outcome, reached by arithmetic rather than
   by a bad checker. Needs a ruling.
3. **`--check` is not a drift check.** Fixing it is coupled to `spine_ref`, which is bound
   to `HEAD` (`cli.py`:52) rather than to the spine document's own last-modifying commit —
   so the committed registry is stale the moment it is committed, and a real comparison
   would fail on every push. The two must be decided together.
4. **`CI-07`'s residue.** After the seeder fixes, the remaining 23 include records whose
   `wp` is established by `06` §6 and which cannot carry a hash `WP-N1-04` has not minted.
   Whether that is a genuine circularity in condition ② is not yet established; the
   BOOT-owned work is done, so the residue is now measurable.
5. **`/`-abbreviated id lists in `06` §6** (`FR-GUI-001`/`002`/`004`) resolve only their
   first id — same family as the range defect, different grammar. Affects `WP-G-00`,
   `WP-G-01`, `WP-G-02`.
6. **`01`'s execution-class citations** for `WP-1-05`/`WP-1-06` disagree with the
   catalogue. No rule covers it: `06`:563 enumerates three comparisons and execution class
   is not among them.
7. **`CI-11b-자기적용`'s module path** derives to `ci_11b_자기적용.py`; the file is
   `ci_11b_self.py`. Only reachable in the dashboard's absent branch, which would falsely
   report `실행체 없음`.
8. Corpus defects from the seeding pass, still open — see
   `2026-07-20_boot01-registry-bootstrap.md` follow-ups.
