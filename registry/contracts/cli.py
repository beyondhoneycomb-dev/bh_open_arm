"""Command-line entry point for the contract index and the freeze lock.

Exposed as `oa-contracts`. There is no `bump` subcommand: `06` §4.3 defines a
change as the publication of `@v(n+1)`, so a bump is `freeze CTR-X@v2` and
giving it a separate verb would imply a second, softer way to change a frozen
contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from registry.contracts.canonical import load_schema
from registry.contracts.index import (
    ContractStore,
    build_index,
    check_wp_start,
    freeze_contract,
    retire_contract,
    verify_index,
    write_index,
)
from registry.contracts.violations import ContractViolationError, Violation

EXIT_OK = 0
EXIT_VIOLATION = 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the contract registry command line.

    Args:
        argv: Argument vector without the program name; defaults to `sys.argv`.

    Returns:
        int: `EXIT_OK` when the command succeeded, `EXIT_VIOLATION` when a
            contract rule was broken.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    store = ContractStore.at(Path(args.repo_root))

    try:
        return _dispatch(args, store)
    except ContractViolationError as violation:
        _report([violation.violation])
        return EXIT_VIOLATION


def _dispatch(args: argparse.Namespace, store: ContractStore) -> int:
    """Execute the selected subcommand.

    Args:
        args: Parsed arguments.
        store: Contract store to operate on.

    Returns:
        int: Process exit status.
    """
    if args.command == "build":
        index = write_index(store)
        frozen = sum(1 for row in index["contracts"] if row["status"] == "FROZEN")
        print(f"wrote {store.index_path} — {len(index['contracts'])} generations, {frozen} frozen")
        return EXIT_OK

    if args.command == "show":
        print(json.dumps(build_index(store), indent=2, ensure_ascii=False))
        return EXIT_OK

    if args.command == "verify":
        return _finish(verify_index(store), "contract index verified against its sources")

    if args.command == "freeze":
        outcome = freeze_contract(store, args.contract_id, load_schema(Path(args.schema)))
        if outcome.already_frozen:
            print(f"{outcome.record.contract_id} already frozen at identical content")
            return EXIT_OK
        print(f"froze {outcome.record.contract_id} at {outcome.record.canonical_hash}")
        if outcome.superseded is not None:
            print(f"superseded {outcome.superseded}")
        for trigger in outcome.triggers:
            print(
                f"  re-verify {trigger.consumer_wp}"
                f" — stale_on {trigger.stale_on}"
                f", replacement {trigger.required_replacement_wp}"
            )
        return EXIT_OK

    if args.command == "retire":
        record = retire_contract(store, args.contract_id)
        print(f"retired {record.contract_id} — consuming it now fails the build")
        return EXIT_OK

    return _finish(
        check_wp_start(store, args.wp_id), f"{args.wp_id} may start — consumed contracts are frozen"
    )


def _finish(violations: list[Violation], success_message: str) -> int:
    """Report the result of a read-only check.

    Args:
        violations: Violations the check produced.
        success_message: Message to print when there are none.

    Returns:
        int: Process exit status.
    """
    if not violations:
        print(success_message)
        return EXIT_OK
    _report(violations)
    return EXIT_VIOLATION


def _report(violations: list[Violation]) -> None:
    """Print violations to stderr in the fixed machine-readable shape.

    Args:
        violations: Violations to print.
    """
    for violation in violations:
        print(json.dumps(violation.as_dict(), ensure_ascii=False), file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser.

    Returns:
        argparse.ArgumentParser: Parser with every subcommand registered.
    """
    parser = argparse.ArgumentParser(
        prog="oa-contracts", description="Contract hash registry and CONTRACT_FROZEN lock."
    )
    parser.add_argument(
        "--repo-root", default=".", help="Repository root holding docs/plan and registry."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("build", help="Regenerate contract_index.json from its sources.")
    subcommands.add_parser("show", help="Print the derived index without writing it.")
    subcommands.add_parser("verify", help="Check the persisted index against its sources.")

    freeze = subcommands.add_parser(
        "freeze", help="Freeze a contract generation, or issue the next one."
    )
    freeze.add_argument("contract_id", help="Contract id in CTR-<NAME>@v<n> form.")
    freeze.add_argument("--schema", required=True, help="Path to the contract schema JSON.")

    retire = subcommands.add_parser(
        "retire", help="Retire a superseded generation once its replacements have landed."
    )
    retire.add_argument("contract_id", help="Superseded contract id in CTR-<NAME>@v<n> form.")

    start = subcommands.add_parser(
        "check-start", help="Check that a work package may start against frozen contracts."
    )
    start.add_argument("wp_id", help="Work package id, e.g. WP-3B-06.")

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
