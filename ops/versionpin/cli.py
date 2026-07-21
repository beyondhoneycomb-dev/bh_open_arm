"""Command line entry point for the version pin, blocker, and runtime reporter.

Three subcommands, each exiting non-zero on a contract violation so the same predicates
hold from a shell as from the test suite:

  * `report`  — emit the four FR-SIM-102 runtime version fields as JSON;
  * `verify`  — run the pin-contract gate on the committed manifest (structure, no
    auto-upgrade, complete report, Isaac pin 5.1/2.3.x);
  * `blocker` — classify one version specifier as exact or a rejected range.
"""

from __future__ import annotations

import argparse
import json
import sys

from ops.versionpin.blocker import classify_specifier
from ops.versionpin.manifest import load_manifest
from ops.versionpin.reporter import report
from ops.versionpin.rollback import gate_checks

EXIT_OK = 0
EXIT_REJECTED = 1


def _cmd_report(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Emit the runtime version report as JSON.

    Args:
        args: Unused; present because every subcommand shares one dispatch signature.

    Returns:
        (int) Exit code; non-zero when a version field could not be resolved.
    """
    versions = report()
    print(json.dumps(versions.as_dict(), ensure_ascii=False, indent=2))
    return EXIT_OK if versions.complete else EXIT_REJECTED


def _cmd_verify(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Run the pin-contract gate on the committed manifest.

    Args:
        args: Unused; present because every subcommand shares one dispatch signature.

    Returns:
        (int) Exit code; non-zero when any gate job fails.
    """
    checks = gate_checks(load_manifest())
    ok = True
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        line = f"{status}\t{check.name}"
        if not check.passed and check.detail:
            line += f"\t{check.detail}"
        print(line)
        ok = ok and check.passed
    return EXIT_OK if ok else EXIT_REJECTED


def _cmd_blocker(args: argparse.Namespace) -> int:
    """Classify a single version specifier.

    Args:
        args: Parsed arguments carrying `specifier`.

    Returns:
        (int) Exit code; non-zero when the specifier is a rejected range.
    """
    verdict = classify_specifier(args.specifier, where="cli")
    print(
        json.dumps(
            {
                "specifier": verdict.specifier,
                "classification": verdict.classification.value,
                "reason": verdict.reason,
            },
            ensure_ascii=False,
        )
    )
    return EXIT_REJECTED if verdict.rejected else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to a subcommand.

    Args:
        argv: Argument vector; defaults to `sys.argv[1:]`.

    Returns:
        (int) Process exit code.
    """
    parser = argparse.ArgumentParser(prog="oa-versionpin", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("report", help="emit the four FR-SIM-102 runtime version fields")
    subparsers.add_parser("verify", help="run the pin-contract gate on the manifest")

    blocker_parser = subparsers.add_parser("blocker", help="classify a version specifier")
    blocker_parser.add_argument("specifier", help="a version specifier, e.g. ==5.1.0 or >=2.3")

    args = parser.parse_args(argv)
    dispatch = {"report": _cmd_report, "verify": _cmd_verify, "blocker": _cmd_blocker}
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
