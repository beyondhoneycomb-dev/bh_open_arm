"""WP-4B-05 — the FR-OPS-089 deployment gate.

Runs the merged contract regression (base Wave 0-Env facts + this band's) through
the checker and the CG-4B-05c ghost-version static check, and exits non-zero if
either finds drift. A LeRobot upgrade that changes any registered fact — or a pin
that is not a commit SHA — blocks deployment here.

Usage:
    python -m backend.compat.contract_regression.cli            # gate, exit 0/1
    python -m backend.compat.contract_regression.cli --json     # machine-readable
"""

from __future__ import annotations

import argparse
import json

from backend.compat.contract_regression import ghost_version, register

EXIT_OK = 0
EXIT_BLOCKED = 1


def main(argv: list[str] | None = None) -> int:
    """Run the deployment gate and report an exit code.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        (int) 0 when every fact holds and the pin is a SHA, 1 otherwise.
    """
    parser = argparse.ArgumentParser(prog="oa-contract-regression", description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)

    regression = register.run()
    ghost = ghost_version.check_ghost_version()
    blocked = not regression.ok or not ghost.ok

    if args.json:
        print(
            json.dumps(
                {
                    "facts": [
                        {
                            "fact_id": row.fact_id,
                            "ok": row.ok,
                            "severity": row.severity,
                            "expected": row.expected,
                            "actual": row.actual,
                            "affected_frs": list(row.affected_frs),
                        }
                        for row in regression.rows
                    ],
                    "registered": list(regression.registered),
                    "ghost_version": {
                        "ok": ghost.ok,
                        "commit_sha": ghost.commit_sha,
                        "resolved_version": ghost.resolved_version,
                        "problems": list(ghost.problems),
                    },
                    "deployment_blocked": blocked,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for row in regression.rows:
            print(row.as_line())
        print(f"\n{regression.summary()}")
        print(ghost.as_line())
        print("DEPLOYMENT BLOCKED" if blocked else "DEPLOYMENT ALLOWED")

    return EXIT_BLOCKED if blocked else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
