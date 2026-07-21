# 2026-07-21 — Wave −1: the specification normalization band

Follows `2026-07-21_band-gate-passed.md`, which opened the BOOT gate. With work packages
now able to start, Wave −1 is the next blocking barrier: it resolves the six documented
specification contradictions into a machine-readable ledger and issues the normalization
hash that gates every downstream start.

## Context

The plan (`02a` §1) makes Wave −1 a global blocking barrier — the same shape as BOOT. Its
job is not to make new decisions: the six contradictions (`NORM-001..004, 006, 007`) were
already adjudicated in `02a` §1.3, with a winner named for each. Wave −1's job is to
**formalize** those rulings into `docs/plan/normalization/ledger.yaml`, verify the discarded
text still exists character-exact in its source, and mint a content hash that downstream
packages must reference to start.

Built as a four-stage background workflow (ledger → gate map → hash → adversarial audit),
following the BOOT pattern. The gate stayed exit 0 GREEN throughout.

## Files changed

Created:

- `registry/normalization/**` — ledger schema, loader, validator, content-hash, gate map,
  start-blocking barrier, stale propagation, CLI, and violation fixtures (WP-N1-01/03/04).
- `docs/plan/normalization/ledger.yaml` — the six rows plus the NORM-005 reference note
  (WP-N1-02).
- `docs/plan/normalization/gate_spec_map.yaml` — `PG-*` ↔ spec-reference mapping (WP-N1-03).
- `docs/plan/normalization/normalization_hash` — the issued content hash (WP-N1-04).
- `tests/n1/**` — 64 tests across the eight modules.

Modified:

- `docs/plan/02a` §1.5 — ownership clauses for the four N1 rows; the winner-cardinality
  correction (below).
- `docs/plan/03` — NORM-005 fix: `PG-CAN-001`'s spec mapping cited the nonexistent `16 M-25`;
  corrected to `15 §2.10 조건7 + 15 §2.1 + 01 NFR-SYS-002`.
- `registry/ingest/build.py` — reads the ledger and stamps `normalization` onto the records
  it settles.

## Why

### The §1.3 rulings had paraphrased their own safety quotes

The ledger's `discarded[].quote` must exist character-exact in the original source, because
these are the discarded *safety* requirements — NORM-006 splits 비상정지 into `STOP_HOLD`
(hold torque) and `POWER_CUT` (drop the arm); NORM-007 removes a GUI control that presumed a
software power-cut boundary the rig does not have. Transcribing them wrong would corrupt the
record of what was deliberately killed.

Building the ledger surfaced that `02a` §1.3 itself paraphrased several of these against
`docs/spec/13`: `FR-GUI-065` rendered `전 화면·전 모드·제어권 무관` where the source says
`모든 화면·모든 모드·제어권 보유 여부와 무관하게`; `NFR-GUI-005` dropped `상한` and `입력`.
The ledger took the **source-exact** text, not §1.3's paraphrase, and reported the
divergence rather than smoothing it over. A related §1.3 error: it attributed the string
`M-2 + M-8` to `docs/spec/12 NFR-SAF-001`, but `M-8` does not occur in `docs/spec/12` at all
— it lives in `docs/spec/15` NFR-PRF-040. The ledger records the real occurrences.

The adversarial audit re-opened `docs/spec/13` and confirmed all six NORM-006/007 quotes are
substring-exact after only markdown-emphasis normalization (the same `plain_text` normalization
every checker applies): words 100% identical, zero paraphrase.

### The winner field is a list, because four of six rulings have plural winners

`02a` §1.2 defines the winner as "a single FR/NFR/D-n ID". Four of the six actual rulings
break that: NORM-002's winner is an invariant carried by two NFRs, NORM-003's is a pair of
gates (`PG-RT-001a`/`PG-RT-001b`), NORM-004's is three D/M entries, NORM-001's is five ids.
The ledger models `winners[]` as a non-empty list, each entry grep-verified against the
corpus, and `02a` §1.5's WP-N1-01 cell was corrected from `ID 1개(0개·2개 금지)` to
`ID의 비어있지 않은 목록(0개 금지)` so the plan no longer contradicts the shipped artifact.
This was the lead's call, recorded for veto.

### CI-07 dropped 22 → 13, and stops there honestly

The seeder now stamps the canonical hash onto every record the ledger settles — 14 records,
all carrying the same content hash. CI-07 went from 22 findings to 13. It was **not** driven
to zero, and forcing it would be the forge this project has caught twice:

- 9 of the 13 are `결정필요`-tagged requirements the six contradictions never touched — real
  decisions that belong to Wave 1 and later.
- 4 (`NFR-PRF-004/054/055`, `NFR-SAF-001`) appear in §1.3's contradiction-description columns
  but not in the ledger's structured winners/discarded. Whether they are NORM-003 winners
  (surviving requirements now expressed via `PG-RT-*`) or contradiction-context CI-07
  over-harvests is a refinement left open — see follow-ups.

So CI-07 remains temporally excluded from the judged range. My earlier expectation — that
Wave −1 would turn CI-07 green and let it be lifted — was too optimistic: the six
contradictions are resolved, but CI-07's full contested population is not, and will not be
until the downstream `결정필요` decisions land.

### The hash is a real function of ledger content

`normalization_hash` is a sha256 over the canonical serialization of `{ledger, gate_map}` —
sorted keys, preserved array order, no field-dropping projection (unlike the contract-freeze
hash, because for data every field is normative). Same content → same hash; one byte changed
→ different hash; key reorder → unchanged. A constant would have forged CI-07; the audit
mutated a winner and confirmed the hash flips.

## Verification

```bash
.venv/bin/python -m registry.check --all              # 0 judged findings — GREEN, exit 0
.venv/bin/python -m pytest -q                         # 541 passed
.venv/bin/python -m ruff check registry ops dashboard tests   # clean
.venv/bin/python -m mypy registry ops dashboard       # 89 source files, clean
.venv/bin/python -m registry.ingest.cli --check       # 1216 records, 177/177
.venv/bin/python -m registry.generate.cli --check     # 182 files match
.venv/bin/python -m registry.normalization.cli --check # 0 schema errors, 0 violations
```

An adversarial auditor tried to prove a safety quote was paraphrased or the hash forged and
could not: hash is content-derived, quotes are source-exact, no checker was touched
(`registry/checks/` byte-identical to HEAD), every new file is owned (CI-02b green).

## Follow-ups

1. **CI-07 cannot be lifted from `JUDGE_EXCLUDED` yet.** It needs the 9 `결정필요` decisions
   (Wave 1+) resolved or deferred. Revisit the lift when those land — the trigger is still
   documented in `registry/checks/__init__.py`.
2. **The 4-record ledger question.** Decide whether `NFR-PRF-004/054/055` and `NFR-SAF-001`
   are NORM-003 winners (they survive, expressed via `PG-RT-*`) and belong in `ledger.yaml`,
   or whether CI-07's ledger branch over-harvests them from §1.3's `모순` column. If the
   former, adding them drops CI-07 to 9.
3. **`02a` §1.5 WP-N1-02 contract names** (`connect_contract`/`mode_contract`/…) disagree with
   §1.3's canonical `CTR-*`/`gate-registry` names. The ledger followed §1.3; the §1.5 prose is
   unreconciled.
4. **`tests/n1` carries 9 mypy-strict errors**, latent because the CI mypy gate scopes to
   `registry ops dashboard`. Consistent with `tests/boot*`; fix if the gate scope ever widens.
