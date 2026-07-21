#!/usr/bin/env bash
# WP-ENV-02 — per-target reproducible install.
#
# The host target (rtx_5080, cp312-x86_64) resolves from the committed uv.lock; the
# other fleet targets are DEFERRED (see targets/matrix.yaml lock_resolution.reason)
# and must be resolved on their own hardware/index — this script refuses to fake it.
#
# Usage: targets/install/reproduce.sh <target_id>
set -euo pipefail

TARGET="${1:-rtx_5080}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

case "$TARGET" in
  rtx_5080|host)
    # Deterministic core plan-machine + robot stack from the universal lock.
    uv sync --frozen --extra dev --extra robot
    ;;
  jetson_nano|jetson_orin|rtx_5090|rtx_a6000)
    echo "target '$TARGET' is DEFERRED on this host — resolve on the target hardware/index." >&2
    echo "reason:" >&2
    python -c "import yaml,sys; m=yaml.safe_load(open('targets/matrix.yaml')); \
t=next(t for t in m['targets'] if t['target_id']=='$TARGET'); \
print('  ' + ' '.join(t['lock_resolution']['reason'].split()), file=sys.stderr)"
    exit 3
    ;;
  a100|h100)
    echo "target '$TARGET' is explicitly EXCLUDED (Isaac unsupported — no RT cores)." >&2
    exit 3
    ;;
  *)
    echo "unknown target: $TARGET" >&2
    exit 2
    ;;
esac
