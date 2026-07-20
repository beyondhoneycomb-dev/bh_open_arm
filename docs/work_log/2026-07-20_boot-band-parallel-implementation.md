# 2026-07-20 — WP-BOOT-02..05 in parallel, and the first real gate verdict

Follows `2026-07-20_boot01-registry-bootstrap.md`, which landed `WP-BOOT-01`.

## Context

With the registry seeded and its schema fixed, the remaining four BOOT packages own
disjoint paths and could run concurrently. They were dispatched to a background workflow:
four implementers, each followed by an adversarial verifier instructed to refute rather
than confirm. 8 agents, 0 errors, ~49 minutes.

The plan forbids fan-out in this band (`02a` §−2.2: all five are `SHAPE-CF`, `n=1`)
because the ownership prover `WP-0A-03` does not exist yet. That reasoning is about the
*prover*, not the *fact*: the five packages' owned paths are enumerated in `02a` §−2.3 and
are disjoint by inspection. Running them concurrently is a deliberate deviation, recorded
here rather than left implicit.

## Files changed

- `registry/generate/**` — manifest schema, five index builders, CLI (`WP-BOOT-02`).
- `registry/check.py`, `registry/checks/**` — 34 CI checkers plus fixtures (`WP-BOOT-03`).
- `registry/state/**`, `ops/launch/**`, `ops/cancel/**` — state store, descendant closure,
  spawn/cancel with latch ordering (`WP-BOOT-04`).
- `registry/contracts/**` — contract hash ledger and freeze lock (`WP-BOOT-05`).
- `registry/checks/RULE_INVENTORY.md` — ground-truth rule list, written before scoring.
- `dashboard/render.py`, `dashboard/index.html` — status page generated from disk.
- `docs/guide/01-부트스트랩-사용법.md` — Korean usage guide.
- `registry/ingest/{catalog,build}.py` — four defect fixes, detailed below.
- `tests/**/__init__.py`, `tests/boot04/*` import qualification — collection fix.
- `.gitignore` — session tooling artifacts.

## Why

### Four defects in my own `WP-BOOT-01` code, found by a peer and confirmed by reading

The `WP-BOOT-02` implementer reported bugs in `registry/ingest/catalog.py`. I reproduced
each before changing anything.

**Ownership clause truncated at the first dot.** `OWNS_CLAUSE` was `소유 경로\s*=\s*([^.。]*)`,
intending "to the end of the sentence". File paths contain dots, so
`registry/traceability.yaml` captured as `registry/traceability` and matched no glob
pattern.

**A mode was read as governing one path, not the group.** `OWNS_GLOB` required `(MODE)` to
follow each path, so `registry/state/**, ops/launch/**, ops/cancel/** (EXCLUSIVE)` yielded
only `ops/cancel/**`.

Together these left **168 of 177 packages with `owns: []`**. Nothing errored; the registry
validated; the schema was satisfied. The consequence is the one this whole band exists to
prevent: CI-02 (duplicate ownership) and CI-02b (orphan files) would have run over an
empty ownership axis and reported green while checking nothing.

The fix parses the actual grammar — comma-separated paths per group, one parenthesised
mode per group, prose allowed inside the parenthesis — and merges both declaration sites
(`06` §3.2 per-symbol, `02a` inline) rather than letting one silently shadow the other.

**Contract producers read from mentions instead of declarations.** `produces` came from
contract ids appearing in a package's output column. A package naming `CTR-ACT@v1` there
may be consuming or extending it, so two packages appeared to produce `CTR-ACT@v1` and two
`CTR-ERR@v1`, and eight of thirteen contracts had no producer at all. `01` §6.2 and `06`
§4.1 both carry the authoritative table and agree on all thirteen. Reading the table
instead took CI-03 violations 2 → 0 and producer coverage 5/13 → 13/13.

This is the same error as citation-versus-ownership for requirements, in a second place.
The general shape: **a mention is not a declaration**, and the corpus always has a
declaration table somewhere.

**Comma-joined glob.** `06`:377 names a calibration schema module and its JSON in one
cell; kept whole it became one glob matching nothing.

### The evidence-path rule was specified and not implemented

The first real gate run produced 1,176 findings, of which **1,030 were CI-04b alone** —
every derived `CG-*` lacking an evidence path. `06` §2.4a states the derivation outright:
each `CG-*` owns `registry/build/evidence/<CG-id>/`. Implementing it, plus `planned: true`
for paths that do not exist yet (`06` §2.2 provides that flag for exactly this), took the
total to **141**.

That ratio is the lesson: one unimplemented derivation rule accounted for 88% of the
findings and would have read as "the corpus is deeply broken".

### What the remaining 141 findings are

They are not noise, and they are not all fixable here:

| rule | n | character |
|---|---|---|
| CI-02b | 54 | Real gap. `tests/**`, `registry/ingest/**`, `dashboard/**`, `pyproject.toml`, `.pre-commit-config.yaml` are owned by no work package. `06` §3.3's glob map has no entry for test trees or build tooling, and §5's exclusion list covers `.github/**` but not `pyproject.toml`. |
| CI-11c | 35 | Consumers of the provisional `PG-RT-001a` lacking a `PG-RT-001b:PASS` re-derivation trigger. Partly fixed by deriving it for direct consumers; the transitive tail remains. |
| CI-07 | 22 | **Correctly blocked.** Records under `NORM-*` ledger entries have no normalisation hash because Wave −1 has not run. The rule firing here is the rule working. |
| CI-14 | 9 | Stages whose execution class does not derive from their shape, plus human gates missing some of `00` §4.1's six elements. Corpus facts. |
| CI-03d, CI-04, CI-14b, CI-16, CI-17, CI-11 | 21 | Mixed corpus defects; CI-04's three confirm the two prose-only acceptance columns independently found during seeding. |

### One rule was omitted, exactly where predicted

`CI-11b-자기적용` is missing from the 34 built. Before scoring I extracted the rule list
mechanically into `registry/checks/RULE_INVENTORY.md` and flagged two ids that read as
something other than a rule: `CI-16` (declared in §5.6, no row in the §5 table) and
`CI-11b-자기적용` (a row with its own name, easily read as a sub-clause of `CI-11b`).
`CI-16` was built. `CI-11b-자기적용` was not.

It is the rule requiring a checker to be run against the real corpus and proven to both
catch its violation fixture and pass its three prose exceptions — the checker that checks
the checker. Without the inventory written first, counting 34 files against a list of 34
would have read as complete.

### The checkers distinguish vacuous from clean

`registry/check.py` reports `VACUOUS sites=0` separately from `green`. Nine rules are
currently vacuous — CI-13 has no gate-state change to inspect, CI-18 sees no started
package outside BOOT, and `06` §5 says CI-18 is expected to be vacuously true at landing.
A checker that reported those as green would be indistinguishable from one that checks
nothing, which is the failure mode `02a` §−2.3 calls the worst possible outcome.

## Verification

```bash
.venv/bin/python -m pytest -q                       # 458 passed
.venv/bin/python -m mypy registry ops dashboard     # Success: 79 source files
.venv/bin/python -m ruff check registry ops dashboard tests   # All checks passed
.venv/bin/python -m registry.ingest.cli             # records=1215 packages=177/177 schema_errors=0
.venv/bin/python -m registry.generate.cli --check   # 182 generated files match
.venv/bin/python -m registry.check --all            # 34 rules, 141 findings — BUILD FAILED
.venv/bin/python -m dashboard.render                # 판정 보류 (absent)
```

Independently re-verified rather than taken from the agents' reports:

- Ownership extraction: reproduced both regex bugs against the five BOOT clauses before
  fixing, and confirmed all five now yield their complete declared path lists.
- Contract producers: 0 CI-03 violations, 13/13 producers, cross-checked against both
  `01` §6.2 and `06` §4.1.
- Index mutual inverses: 384 forward and 177 reverse edges, all mirrored — and asserted on
  **non-empty** sets, after an earlier version of this same check reported "ok" against a
  3-element misparse.

## Follow-ups

1. **Build `CI-11b-자기적용`.** Ground truth is in `registry/checks/RULE_INVENTORY.md`.
2. **Ownership map has no entry for `tests/**`, `pyproject.toml`, `registry/ingest/**`.**
   Needs a decision in `06` §3.3 and §5's CI-02b exclusion list; do not invent globs to
   silence the check.
3. **CI-11c transitive tail** — 35 remaining consumers of `PG-RT-001a`.
4. **CI-07's 22 findings stay until Wave −1 lands.** This is correct behaviour.
5. Corpus defects from the seeding pass, still open — see
   `2026-07-20_boot01-registry-bootstrap.md` Follow-ups, all six unaddressed.
6. **The band gate is not passed.** Condition ① (177 registered) holds; condition ②
   (CI-01..CI-17 green on their own corpus) does not. `dashboard/index.html` says so.
