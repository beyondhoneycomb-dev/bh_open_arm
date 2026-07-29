#!/usr/bin/env bash
# Every gate, in one run. This replaced the GitHub Actions pipeline: the pipeline was removed
# because a research-stage project pays its cost on every push and reads its result never.
#
# The list is the whole contract — a gate that is not here is a gate nobody runs. Two of these
# were missing from the habit that preceded this script and went unnoticed for days:
# `registry.env.cli --verify-issued` and `registry.generate.cli --check`.
#
# Exit code is what to trust. Reading the tail of the output is how green was reported over a
# red tree before.
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
run "pytest"                 python3 -m pytest -q tests scripts

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
