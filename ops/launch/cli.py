"""Command line entry point for the state store, closure calculator and spawn adapter.

Registered as `oa-state`. Every subcommand exits non-zero on a rejected operation, so the same
predicates hold from a shell as from the test suite.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ops.cancel.staticcheck import find_external_latch_calls
from ops.launch.manifest import ManifestError, load_manifest
from registry.state.closure import descendant_closure, load_graph
from registry.state.model import (
    LEGAL_TRANSITIONS,
    IllegalTransitionError,
    WorkPackageState,
)
from registry.state.store import StateStore, StateStoreError

EXIT_OK = 0
EXIT_REJECTED = 1


def _cmd_states(args: argparse.Namespace) -> int:
    """Print the recorded state of every work package.

    Args:
        args: Parsed arguments carrying `state_dir`.

    Returns:
        (int): Process exit code.
    """
    store = StateStore(Path(args.state_dir))
    for wp, state in sorted(store.all_states().items()):
        print(f"{wp}\t{state.value}")
    return EXIT_OK


def _cmd_transition(args: argparse.Namespace) -> int:
    """Move one work package to a new state.

    Args:
        args: Parsed arguments carrying the transition's five fields.

    Returns:
        (int): Process exit code; non-zero when the transition is rejected.
    """
    store = StateStore(Path(args.state_dir))
    try:
        record = store.transition(
            wp=args.wp,
            new_state=WorkPackageState(args.to),
            trigger=args.trigger,
            evidence_hash=args.evidence_hash,
        )
    except (IllegalTransitionError, StateStoreError) as error:
        print(f"REJECTED: {error}", file=sys.stderr)
        return EXIT_REJECTED
    print(json.dumps(record.to_json(), ensure_ascii=False))
    return EXIT_OK


def _cmd_transitions(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Print the legal transition table.

    Args:
        args: Unused; present because every subcommand shares one dispatch signature.

    Returns:
        (int): Process exit code.
    """
    for previous, new in sorted(LEGAL_TRANSITIONS):
        print(f"{previous.value} -> {new.value}")
    return EXIT_OK


def _cmd_log(args: argparse.Namespace) -> int:
    """Print the transition log.

    Args:
        args: Parsed arguments carrying `state_dir`.

    Returns:
        (int): Process exit code.
    """
    store = StateStore(Path(args.state_dir))
    for record in store.transitions():
        print(json.dumps(record.to_json(), ensure_ascii=False))
    return EXIT_OK


def _cmd_closure(args: argparse.Namespace) -> int:
    """Print the transitive descendant closure of a trigger.

    Args:
        args: Parsed arguments carrying `registry` and `trigger`.

    Returns:
        (int): Process exit code.
    """
    graph = load_graph(Path(args.registry))
    closure = descendant_closure(graph, args.trigger)
    payload = {
        "trigger": closure.trigger,
        "wps": sorted(closure.wps),
        "depth": {wp: closure.depth[wp] for wp in sorted(closure.depth)},
        "artifacts": [
            {"id": item.id, "kind": item.kind, "path": item.path, "wp": item.wp}
            for item in closure.artifacts
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return EXIT_OK


def _cmd_shape(args: argparse.Namespace) -> int:
    """Print the fan-out shape a manifest resolves to, per stage.

    Args:
        args: Parsed arguments carrying `manifest`.

    Returns:
        (int): Process exit code; non-zero when the manifest is rejected.
    """
    try:
        manifest = load_manifest(Path(args.manifest))
    except ManifestError as error:
        print(f"REJECTED: {error}", file=sys.stderr)
        return EXIT_REJECTED
    for stage in manifest.stages:
        print(
            f"{manifest.wp_id}\tstage {stage.index}\t{stage.workflow.value}"
            f"\t{stage.exec_class.value}\t{stage.cancel_policy.value}\tn={stage.fanout()}"
        )
    return EXIT_OK


def _cmd_check_latch(args: argparse.Namespace) -> int:
    """Report latch call sites outside the package that owns the latch path.

    Args:
        args: Parsed arguments carrying `root`.

    Returns:
        (int): Process exit code; non-zero when any hit is found.
    """
    violations = find_external_latch_calls(Path(args.root))
    for violation in violations:
        print(str(violation), file=sys.stderr)
    if violations:
        print(f"REJECTED: {len(violations)} external latch call(s)", file=sys.stderr)
        return EXIT_REJECTED
    print("0 external latch call sites")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser.

    Returns:
        (argparse.ArgumentParser): Parser with every subcommand registered.
    """
    parser = argparse.ArgumentParser(prog="oa-state", description=__doc__)
    parser.add_argument(
        "--state-dir",
        default="registry/state/store",
        help="directory holding the state document",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("states", help="print recorded states").set_defaults(func=_cmd_states)
    subparsers.add_parser("log", help="print the transition log").set_defaults(func=_cmd_log)
    subparsers.add_parser("transitions", help="print the legal transition table").set_defaults(
        func=_cmd_transitions
    )

    transition = subparsers.add_parser("transition", help="move a work package to a new state")
    transition.add_argument("wp")
    transition.add_argument("--to", required=True, choices=[s.value for s in WorkPackageState])
    transition.add_argument("--trigger", required=True)
    transition.add_argument("--evidence-hash", required=True)
    transition.set_defaults(func=_cmd_transition)

    closure = subparsers.add_parser("closure", help="enumerate a trigger's descendant closure")
    closure.add_argument("trigger")
    closure.add_argument("--registry", default="registry/traceability.yaml")
    closure.set_defaults(func=_cmd_closure)

    shape = subparsers.add_parser("shape", help="print a manifest's resolved fan-out shape")
    shape.add_argument("manifest")
    shape.set_defaults(func=_cmd_shape)

    check_latch = subparsers.add_parser(
        "check-latch", help="find latch call sites outside ops/cancel"
    )
    check_latch.add_argument("--root", default=".")
    check_latch.set_defaults(func=_cmd_check_latch)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface.

    Args:
        argv: Argument vector; defaults to `sys.argv[1:]`.

    Returns:
        (int): Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
