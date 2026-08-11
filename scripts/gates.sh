#!/usr/bin/env bash
# Every gate, in one run. This script is the whole gate story for this repository: there is no
# hosted pipeline, because a research-stage project pays a pipeline's cost on every push and
# reads its result never.
#
# The list below is the contract — a gate that is not on it is a gate nobody runs. Anything that
# has to hold before a commit belongs here and nowhere else.
#
# Exit code is the verdict, and the only verdict. The output ends with a green banner even when a
# gate above it failed, so a reader who checks the tail instead of the code reports green over a
# red tree.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
[ -d .venv ] && source .venv/bin/activate

FAILED=()

run() {
    local name="$1"
    shift
    printf '\n=== %s ===\n' "$name"
    if "$@"; then
        return 0
    fi
    FAILED+=("$name")
}

run "ruff (lint)"            ruff check .
run "ruff (format)"          ruff format --check .
run "mypy"                   mypy registry ops dashboard
# `scripts/` is a separate invocation, not another word on the line above. It has no
# `__init__.py`, so mypy needs `--explicit-package-bases` to name `scripts.torque_session` the
# way the shell entry point imports it; and its imports reach `backend`, `sim`, `packages` and
# `contracts`, which carry errors of their own and are not in any mypy gate — `--follow-imports`
# keeps those analyzed for types and out of this verdict.
run "mypy (scripts)"         mypy --explicit-package-bases --follow-imports=silent scripts
run "registry corpus"        python3 -m registry.ingest.cli --check
run "registry indexes"       python3 -m registry.generate.cli --check
run "registry rules"         python3 -m registry.check --all
run "normalization ledger"   python3 -m registry.normalization.cli --check
run "contract index"         python3 -m registry.contracts.cli verify
run "env hash"               python3 -m registry.env.cli --verify-issued
run "declared imports"       python3 -m registry.env.declared_imports
run "lockfile is current"    uv lock --check
# Both trees are named because `testpaths` is `tests` alone. The runner in `scripts/` is
# covered by tests that live beside it: `scripts/**` is the only ownership glob WP-ENV-03
# declares, and CI-02b refuses a file under `tests/` that no glob claims.
#
# Two lanes, and the split is not a speed tuning — it is what keeps the parallel lane honest.
# Four files assert on a measured wall-clock duration (`serial` in pyproject, and each file says
# which number it measures); under load they fail on a healthy tree, because the contention is
# what changed the number. Running them anyway and calling the red "flaky" is how a gate stops
# being read. So they get the machine to themselves.
#
# The serial lane runs FIRST, and that order is the point rather than a preference. `tests/wp3d01`
# asserts a p99 over 200 samples, so one scheduling outlier is the verdict; run after the parallel
# lane it saw p99 = 56 ms against a 33 ms bound with p50 still at 1.4 ms — the machine had not
# settled from twenty-four workers. Everything above this line is single-core and takes seconds,
# which is the quietest this script ever is.
#
# `--dist loadfile` keeps a whole file on one worker: module- and session-scoped fixtures are
# shared within a file, and per-test distribution rebuilds them on every worker that draws a test.
run "pytest (serial)"        python3 -m pytest -q tests scripts -m serial
run "pytest (parallel)"      python3 -m pytest -q tests scripts -n auto --dist loadfile -m "not serial"

printf '\n=== frontend ===\n'
if [ -d frontend/node_modules ]; then
    (cd frontend && npx tsc --noEmit) || FAILED+=("tsc")
    (cd frontend && npx vitest run) || FAILED+=("vitest")
else
    echo "SKIPPED — frontend/node_modules absent; run 'npm ci' in frontend/ first"
    FAILED+=("frontend (not installed)")
fi

printf '\n========================================\n'
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "ALL GATES GREEN"
    exit 0
fi
printf 'FAILED: %s\n' "${FAILED[*]}"
exit 1
