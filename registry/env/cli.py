"""Command-line entry point for the WP-ENV-04 environment artifacts.

Usage:
    python -m registry.env.cli --check              # run upstream contract regression
    python -m registry.env.cli --issue              # (re)publish env_hash.txt
    python -m registry.env.cli --verify-issued       # fail if env_hash.txt is stale
    python -m registry.env.cli --barrier M.yaml     # start-block one WP manifest

`--check` imports the pinned upstream and runs every predicate in
`contracts/upstream_facts.yaml`; it is the only sub-command that needs the robot
stack. `--issue`/`--verify-issued`/`--barrier` are light: `CHECKER_VERSION` is a
module constant (the heavy imports live inside the predicates), so importing
`registry.env.upstream` for the version does not pull the robot stack.

Exit status is the contract: non-zero on any failed fact, a stale issued hash, or
a blocked manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from registry.env import env_hash as eh
from registry.env import upstream
from registry.env.barrier import check_manifest

EXIT_OK = 0
EXIT_VIOLATIONS = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
PIN_PATH = REPO_ROOT / "deps" / "lerobot.pin"
FACTS_PATH = REPO_ROOT / "contracts" / "upstream_facts.yaml"


def _pin_sha(pin_path: Path) -> str:
    """Read the pinned LeRobot commit SHA from the pin document.

    Args:
        pin_path: Path to `deps/lerobot.pin`.

    Returns:
        (str) The `commit_sha` field.
    """
    document = json.loads(pin_path.read_text(encoding="utf-8"))
    return str(document.get("commit_sha", ""))


def _inputs(pin_path: Path, lock_path: Path) -> eh.EnvInputs:
    """Assemble the three env-hash inputs from the pin, lock, and checker.

    Args:
        pin_path: Path to `deps/lerobot.pin`.
        lock_path: Path to `uv.lock`.

    Returns:
        (EnvInputs) pin_sha, lock_hash, checker_version.
    """
    return eh.EnvInputs(
        pin_sha=_pin_sha(pin_path),
        lock_hash=eh.lock_hash_of(lock_path),
        checker_version=upstream.CHECKER_VERSION,
    )


def _run_check(args: argparse.Namespace) -> int:
    """Run the upstream contract-regression facts and report.

    Args:
        args: Parsed arguments.

    Returns:
        (int) Non-zero when any fact fails.
    """
    document = yaml.safe_load(args.facts.read_text(encoding="utf-8")) or {}
    rows = upstream.run_facts(document)
    failed = [row for row in rows if not row.ok]
    blocking = [row for row in failed if row.severity == upstream.SEVERITY_FAIL_BLOCKING]

    if args.json:
        print(
            json.dumps(
                {
                    "checker_version": upstream.CHECKER_VERSION,
                    "facts": [
                        {
                            "fact_id": r.fact_id,
                            "ok": r.ok,
                            "severity": r.severity,
                            "expected": r.expected,
                            "actual": r.actual,
                            "affected_frs": list(r.affected_frs),
                        }
                        for r in rows
                    ],
                    "green": not failed,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for row in rows:
            print(row.as_line())
        verdict = "GREEN" if not failed else "FAILED"
        print(
            f"\n{len(rows)} fact(s), {len(failed)} failed "
            f"({len(blocking)} FAIL_BLOCKING) — {verdict}"
        )
    return EXIT_OK if not failed else EXIT_VIOLATIONS


def _run_issue(args: argparse.Namespace) -> int:
    """Compute and publish the env hash.

    Args:
        args: Parsed arguments.

    Returns:
        (int) Always zero; issuance cannot fail once pin and lock are readable.
    """
    inputs = _inputs(args.pin, eh.LOCK_PATH)
    digest = eh.env_hash(inputs)
    eh.write_issued(eh.ISSUED_PATH, digest, inputs)
    print(digest)
    return EXIT_OK


def _run_verify_issued(args: argparse.Namespace) -> int:
    """Fail when the published env hash does not match a fresh recomputation.

    Args:
        args: Parsed arguments.

    Returns:
        (int) Non-zero when the issued file is stale or missing.
    """
    expected = eh.env_hash(_inputs(args.pin, eh.LOCK_PATH))
    published = eh.read_issued(eh.ISSUED_PATH)
    if published == expected:
        print(f"env_hash current: {expected}")
        return EXIT_OK
    print(
        f"env_hash STALE: published {published} but inputs hash to {expected}; run --issue",
        file=sys.stderr,
    )
    return EXIT_VIOLATIONS


def _run_barrier(args: argparse.Namespace) -> int:
    """Refuse a manifest that cites no env hash or a superseded one.

    Args:
        args: Parsed arguments carrying the manifest path.

    Returns:
        (int) Non-zero when the manifest is blocked from starting.
    """
    issued = eh.read_issued(eh.ISSUED_PATH) or eh.env_hash(_inputs(args.pin, eh.LOCK_PATH))
    manifest = yaml.safe_load(args.barrier.read_text(encoding="utf-8")) or {}
    verdict = check_manifest(manifest, issued)
    print(verdict.as_line(), file=sys.stderr if verdict.blocked else sys.stdout)
    return EXIT_VIOLATIONS if verdict.blocked else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Dispatch to the requested environment action.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        (int) Process exit status.
    """
    parser = argparse.ArgumentParser(prog="oa-env", description=__doc__)
    parser.add_argument("--check", action="store_true", help="run upstream contract regression")
    parser.add_argument("--issue", action="store_true", help="publish the env hash")
    parser.add_argument(
        "--verify-issued", action="store_true", help="fail if env_hash.txt is stale"
    )
    parser.add_argument("--barrier", type=Path, help="start-block one WP manifest")
    parser.add_argument("--facts", type=Path, default=FACTS_PATH, help="upstream facts YAML")
    parser.add_argument("--pin", type=Path, default=PIN_PATH, help="lerobot pin JSON")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)

    if args.issue:
        return _run_issue(args)
    if args.verify_issued:
        return _run_verify_issued(args)
    if args.barrier is not None:
        return _run_barrier(args)
    return _run_check(args)


if __name__ == "__main__":
    sys.exit(main())
