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
    (cd frontend && npx eslint .) || FAILED+=("eslint")
    (cd frontend && npx vitest run) || FAILED+=("vitest")
    # `vite build` rather than `npm run build`: that script is `tsc --noEmit && vite build`,
    # and the typecheck above already ran. The bundle is what a type error cannot catch —
    # a resolve failure, a transform error, an asset the CSP plugin cannot inject into.
    #
    # It builds into a scratch directory rather than frontend/dist/, and that is the whole
    # point of the two extra lines: `oa-serve` mounts frontend/dist/ when it exists
    # (backend/config/serve.py), so a gate that wrote there would silently change what a
    # running deployment serves — a check would become a deploy. Producing the served
    # bundle is `npm run build`, deliberately a different command.
    #
    # The `-n` guard is not defensive habit. This script does not `set -e`, so a failed
    # `mktemp -d` leaves GATE_BUNDLE_DIR set to the empty string rather than unset, and
    # `--outDir ""` resolves to the Vite root — `frontend/` itself. Vite calls that a
    # warning, not an error ("build.outDir must not be the same directory of root"), and
    # then `--emptyOutDir` empties it. A full temp filesystem would delete src/.
    if GATE_BUNDLE_DIR="$(mktemp -d)" && [ -n "$GATE_BUNDLE_DIR" ]; then
        (cd frontend && npx vite build --outDir "$GATE_BUNDLE_DIR" --emptyOutDir) \
            || FAILED+=("vite build")
        rm -rf "$GATE_BUNDLE_DIR"
    else
        echo "SKIPPED — mktemp -d failed; refusing to build into the source tree"
        FAILED+=("vite build (no scratch dir)")
    fi
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
