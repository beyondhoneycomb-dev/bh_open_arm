# 2026-07-20 — WP-BOOT-01: seed the traceability registry from the planning corpus

## Context

The repository held only documents: 18 specification files and 10 planning files, no code.
The plan (`docs/plan/00` §3.5, `02a` §−2) makes Wave −2 `BOOT` a hard blocking barrier —
until its five work packages land, no other work package may start (`FAIL_BLOCKING`).
`WP-BOOT-01` is the first of the five: it must register every issued work package in
`registry/traceability.yaml` against a JSON Schema, and produce a prose-to-registry
reconciliation report.

The plan states the band acceptance condition as "all 177 work packages registered +
`CI-01`..`CI-17` green on their own corpus". This session delivers the registry half.
`WP-BOOT-02`..`05` were dispatched in parallel to a background workflow.

## Files changed

Created:

- `pyproject.toml` — uv project, ruff (line 100, `E/F/W/I/N/UP/B/SIM/PTH/RET/ARG/C4`),
  mypy strict, pytest. The repository previously had **no** linter, formatter, type
  checker, CI, or pre-commit configuration at all.
- `.github/workflows/ci.yml` — two jobs: `quality` (lint/format/types/tests) and
  `registry` (re-seed and diff, generated-file check, band acceptance gate at `--through CI-17`).
- `.pre-commit-config.yaml` — ruff, whitespace/JSON/YAML hygiene, plus a local hook
  rejecting hand-edits to `registry/build/**`.
- `registry/ingest/markdown.py` — pipe-table reader. Code-span-aware markup stripping,
  ragged-row rejection, unescaped-pipe recovery, `find_pipe_defects`.
- `registry/ingest/catalog.py` — extracts all 177 work packages from `02a`..`02d`.
  Three layout extractors plus a dispatcher.
- `registry/ingest/spec.py` — extracts 1,207 declared requirements from `docs/spec/`
  declaration tables, with priority and tag normalisation.
- `registry/ingest/resolve.py` — requirement→package ownership resolution, four rules.
- `registry/ingest/build.py` — assembles registry records and the build report.
- `registry/ingest/cli.py` — `python -m registry.ingest.cli [--check]`.
- `registry/schema/traceability.schema.json` — the executable form of `06` §2.2.
- `registry/traceability.yaml` — 1,215 records (generated, 1.0 MB).
- `registry/build/reconciliation.md` — generated reconciliation report.
- `tests/boot01/test_markdown.py`, `tests/boot01/test_registry.py` — 43 tests.

## Why

**The registry is generated, not hand-written.** 177 packages × 6 axes is ~1,000 fields.
Hand-authoring them guarantees silent errors. The plan already demands a
"prose↔registry reconciliation report" as a `WP-BOOT-01` deliverable, and the most honest
way to produce that report is as the diff output of a deterministic parser. The direction
is one-way and time-bounded: prose is input only during bootstrap; after landing, the
registry is canonical and prose is a view of it (`05` §0.1).

**Three table layouts, so three extractors — not one configurable reader.** `02a` uses a
9-column row per package, `02b`/`02d` split the record across a 6-column and a 5-column
table joined on id, `02c` uses a vertical `| 항목 | 내용 |` card per package with the id in
the heading. Three concrete instances exist in the corpus today, so the seam location is
observed rather than guessed.

**Markup stripping had to become code-span-aware.** The first implementation deleted
`` ` ``, `*` and `_` by character class. That silently corrupted the two things that matter
most: `registry/schema/**` became `registry/schema/` (destroying the glob that the entire
ownership-overlap check rests on), and 449 snake_case identifiers lost their underscores
(`send_action` → `sendaction`). The corpus writes literals inside backticks and emphasis
outside them, so honouring that boundary separates the two cases exactly.

**Requirements are parsed from declaration tables, never from prose.** `CI-01` as written
in `06` §5 specifies a regex sweep of `docs/spec/`. Run literally, it harvests 68 ids that
exist only inside sentences *explaining the id format* — `docs/spec/00` §5.1 discusses
`NFR-NFR-001` as a naming counter-example, and the regex cannot tell an illustration from
a declaration. The plan itself already named this trap (NORM-003: "checkers parse field
values, they do not run regex over prose") but `CI-01`'s own text violates it.

**The requirement→package ownership function does not exist in the corpus.** The catalogs
cite requirements as justification, which is many-to-many — `NFR-SAF-007` is cited by
eight packages because eight must respect it. The registry needs many-to-one ownership.
`06` §6 gives per-domain rules plus 47 representative assignments and says explicitly that
the exhaustive list lives in the registry, i.e. in the artifact being bootstrapped. So
ownership is resolved by four rules of decreasing authority, each recorded per record in
`provenance.wp_rule`:

| rule | count | basis |
|---|---|---|
| `doc06-section6` | 47 | `06` §6 names the owner outright |
| `sole-citation` | 295 | exactly one package cites it — no choice to make |
| `coverage-fill` | 34 | several candidates, and one of them would otherwise have zero records |
| `ambiguous-citation` | 89 | several candidates, no stated owner → `DEFERRED` |
| `uncited` | 742 | no package cites it → `DEFERRED` |
| `plan-axis` | 8 | requirements cannot reach it → `PLAN-<band>-<nn>` |

`coverage-fill` deserves the most scrutiny, because it is the one rule that resolves an
ambiguity rather than reading a stated fact. It exists because records are keyed by
requirement while the acceptance condition is stated per package: a package whose every
cited requirement was claimed by a sibling ends up with no record and the 177 count fails.
The tie is broken using two things the corpus does state — the candidate list, and the
"all 177 registered" requirement — and it only ever converts `ambiguous-citation`, never
overriding an earlier rule.

**831 requirements are registered as `wp: DEFERRED`, deliberately.** The schema provides
that value precisely for "registered but unassigned": `CI-04` (gate required) and `CI-07`
(normalisation hash required) both exempt it. Inventing owners for those 831 would make
the registry validate, report green, and be wrong in a way no checker could ever see —
which is the exact failure the plan calls out as worse than having no rule at all
(`02a` §−2.3: "a checker green while catching nothing forges evidence").

**Out-of-vocabulary tags map to `미확인`, not `확정`.** 101 requirements carry a status
marker outside the schema's four values (`개정—검토권고`, `선택`, `정본`). Both fallbacks are
guesses, but they fail in opposite directions: defaulting to `확정` promotes unverified
requirements to confirmed and removes scrutiny they never earned. The original marker is
preserved in `provenance`.

**Plan-axis records generalise beyond the BOOT band.** `00` §8.2a defines
`PLAN-<band>-<nn>` for the plan's own machinery and names only `PLAN-BOOT-*`. Three
further packages (`WP-ENV-02`, `WP-N1-04`, `WP-OPS-03`) are unreachable from any
requirement for the same structural reason. Extending the axis to them preserves its
meaning; the alternative — inventing an `FR-*` — violates `CI-01b` directly.

## Verification

```bash
.venv/bin/python -m registry.ingest.cli
# records=1215 packages=177/177 schema_errors=0

.venv/bin/python -m pytest tests/boot01 -q        # 43 passed
.venv/bin/python -m ruff check registry/ingest tests/boot01   # All checks passed
.venv/bin/python -m mypy registry/ingest          # Success: no issues found in 7 source files
```

Cross-checks that make the extraction trustworthy rather than merely successful:

- The parser's 177 independently reproduces the total asserted in four separate documents
  (`01` §3.2 "총계는 177", `00` §3.5, `05` §0.1, `06` §1.1) and `02c`'s own per-band
  subtotal of 36 (`02c`:950).
- Round-trip difference is zero in both directions: no issued id is missing from the
  registry, and the registry invents none.
- Determinism: two consecutive runs produce byte-identical output
  (`sha256 3bd8ad8d…f1055`); asserted in `test_seeding_is_deterministic`.
- Schema fixture corpus: 10 violation fixtures rejected, 4 pass fixtures accepted. The
  discriminating pair is bare `PG-RT-001` rejected while `PG-RT-001a` is accepted — the
  ban is on the unsplit id, not on the gate family, and over-blocking would break the ~18
  legitimate family references in `00` and `04`.

Four requirements I initially reported as undeclared (`FR-CAM-002`, `FR-REC-014`,
`NFR-PRF-054`, `NFR-PRF-055`) turned out to be **my extraction bugs, not corpus defects** —
confirmed by opening each declaration site. Two needed id matching *within* the cell rather
than against the whole cell (`| **NFR-PRF-055** 🆕 |`), two needed the unescaped-pipe
recovery. Reporting them as document defects would have been a false finding.

## Follow-ups

Defects found in the planning corpus, enumerated with locations in
`registry/build/reconciliation.md` §3 — these need a human, not a code change:

1. **9 table rows with an unescaped pipe inside a code span** — they render with shifted
   columns in any conforming Markdown viewer. `04:414`, `04:467`, `05:717`, `06:314`,
   `07:558`, `07:570`, `12:621`, `12:745`, `12:787`.
2. **6 requirements whose priority cell is `—`** rather than `M`/`S`/`C`
   (`FR-GUI-043`, `FR-GUI-094`, `FR-SAF-012`, `FR-SIM-041`, `NFR-PRF-019`, `NFR-PRF-020`).
3. **101 requirements with an out-of-vocabulary status tag.**
4. **2 packages with zero numbered acceptance items** — `WP-2A-06` and `WP-2C-06`. `CG-*`
   ids are derived positionally from those items (`06` §2.4a), so neither can produce a
   gate, and `CI-04` (no gate = build failure) will flag both. Both are measurement
   packages whose acceptance is stated as prose ("histogram produced; no numeric pass line
   before measurement"). The prose is correct in substance; it just is not enumerated.
5. **`CI-01`'s specified regex contradicts NORM-003.** The rule text mandates a prose
   regex; the rule it must not break says checkers parse field values. `06` §5 line 534
   needs amending, or `CI-01` needs an explicit declaration-table scope.
6. **`WP-*-G1` is a fourth id form** (`WP-4A-G1`, `WP-4C-G1`, issued by `02c` §1.9/§3.8)
   that the id convention tables in `02a` §0.1 and `06` §2.2 do not list.

Open work in this session's scope:

- `WP-BOOT-02`..`05` running in a background workflow with adversarial verification.
- Band acceptance gate and the report dashboard (task #7) depend on `WP-BOOT-03` landing.
- `docs/guide/` Korean usage guide still to write.
- `registry/build/` is currently generated but `registry/build/manifests/**` is owned by
  `WP-BOOT-02`; the CI job references `registry.generate.cli` which that package creates.
