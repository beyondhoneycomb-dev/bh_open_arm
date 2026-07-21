"""Command-line entry point for the Wave -1 normalization artifacts.

Usage:
    python -m registry.normalization.cli --check          # validate ledger + map + issuance
    python -m registry.normalization.cli --check --json   # machine-readable
    python -m registry.normalization.cli --issue          # (re)publish the normalization hash
    python -m registry.normalization.cli --barrier M.yaml # start-block one WP manifest

`--check` validates two artifacts against the live corpus — the contradiction
ledger (`docs/plan/normalization/ledger.yaml`) and the gate ID namespace mapping
(`docs/plan/normalization/gate_spec_map.yaml`) — and, for the real corpus, that the
published normalization hash still matches their content. `--issue` recomputes and
republishes that hash. `--barrier` refuses a manifest that declares no hash or an
out-of-date one. Exit status is the contract: non-zero on any failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from registry.normalization import gate_map
from registry.normalization.barrier import check_manifest
from registry.normalization.content_hash import ISSUED_PATH, issue, read_issued, write_issued
from registry.normalization.loader import LEDGER_PATH, load_ledger, schema_errors
from registry.normalization.validator import Corpus, validate

EXIT_OK = 0
EXIT_VIOLATIONS = 1

ISSUED_KEY = "issued"


def _issued_drift(ledger_path: Path, gate_map_path: Path) -> list[str]:
    """Report whether the published hash is out of date for the real corpus.

    The check runs only for the default ledger and map: a run over a fixture
    ledger is validating that fixture, not the published corpus, so comparing it
    to the issued file would be a category error.

    Args:
        ledger_path: Path the ledger was loaded from.
        gate_map_path: Path the gate map was loaded from.

    Returns:
        (list[str]) One drift message, or empty when current or not applicable.
    """
    if ledger_path != LEDGER_PATH or gate_map_path != gate_map.GATE_MAP_PATH:
        return []
    expected = issue(ledger_path, gate_map_path)
    published = read_issued(ISSUED_PATH)
    if published == expected:
        return []
    return [f"published {published} but corpus hashes to {expected}; run --issue"]


def check(
    root: Path, ledger_path: Path, gate_map_path: Path
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Run schema, semantic and issuance validation over the ledger and the map.

    Semantic validation of an artifact is skipped when it does not even match its
    schema: reasoning about a shape-invalid document reports noise. The corpus is
    resolved once and shared, because both artifacts are validated against it.

    Args:
        root: Repository root the corpus is resolved from.
        ledger_path: Path to the ledger YAML.
        gate_map_path: Path to the gate mapping YAML.

    Returns:
        (tuple[dict[str, list[str]], dict[str, list[str]]]) Schema errors and
        semantic violations, each keyed by artifact name (`ledger`, `gate_map`,
        and `issued` for the published-hash drift).
    """
    corpus = Corpus.load(root)

    ledger_document = load_ledger(ledger_path)
    ledger_schema = schema_errors(ledger_document)
    ledger_violations = (
        [] if ledger_schema else [v.as_line() for v in validate(corpus, ledger_document)]
    )

    map_document = gate_map.load_gate_map(gate_map_path)
    map_schema = gate_map.schema_errors(map_document)
    map_violations = (
        [] if map_schema else [v.as_line() for v in gate_map.validate(corpus, map_document)]
    )

    schema = {"ledger": ledger_schema, "gate_map": map_schema}
    violations = {
        "ledger": ledger_violations,
        "gate_map": map_violations,
        ISSUED_KEY: _issued_drift(ledger_path, gate_map_path),
    }
    return schema, violations


def _run_check(args: argparse.Namespace) -> int:
    """Validate the ledger, the map and the issuance and report.

    Args:
        args: Parsed arguments.

    Returns:
        (int) Process exit status; non-zero when anything is invalid.
    """
    schema, violations = check(args.root, args.ledger, args.gate_map)
    schema_count = sum(len(messages) for messages in schema.values())
    violation_count = sum(len(lines) for lines in violations.values())
    green = schema_count == 0 and violation_count == 0

    if args.json:
        print(
            json.dumps(
                {
                    "ledger": str(args.ledger),
                    "gate_map": str(args.gate_map),
                    "schema_errors": schema,
                    "violations": violations,
                    "green": green,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for artifact, messages in schema.items():
            for message in messages:
                print(f"SCHEMA  [{artifact}] {message}")
        for artifact, lines in violations.items():
            for line in lines:
                print(f"VIOLATION  [{artifact}] {line}")
        verdict = "GREEN" if green else "FAILED"
        print(f"\n{schema_count} schema error(s), {violation_count} violation(s) — {verdict}")

    return EXIT_OK if green else EXIT_VIOLATIONS


def _run_issue(args: argparse.Namespace) -> int:
    """Recompute and publish the normalization hash.

    Args:
        args: Parsed arguments.

    Returns:
        (int) Always zero; issuance cannot fail once the artifacts parse.
    """
    digest = issue(args.ledger, args.gate_map)
    write_issued(ISSUED_PATH, digest)
    print(digest)
    return EXIT_OK


def _run_barrier(args: argparse.Namespace) -> int:
    """Refuse a manifest that cites no normalization hash or a stale one.

    Args:
        args: Parsed arguments carrying the manifest path.

    Returns:
        (int) Non-zero when the manifest is blocked from starting.
    """
    issued = read_issued(ISSUED_PATH) or issue(args.ledger, args.gate_map)
    with args.barrier.open(encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle) or {}
    verdict = check_manifest(manifest, issued)
    print(verdict.as_line(), file=sys.stderr if verdict.blocked else sys.stdout)
    return EXIT_VIOLATIONS if verdict.blocked else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Dispatch to the requested normalization action.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        (int) Process exit status.
    """
    parser = argparse.ArgumentParser(prog="oa-normalize", description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the artifacts")
    parser.add_argument("--issue", action="store_true", help="publish the normalization hash")
    parser.add_argument("--barrier", type=Path, help="start-block one WP manifest")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH, help="ledger YAML path")
    parser.add_argument(
        "--gate-map", type=Path, default=gate_map.GATE_MAP_PATH, help="gate mapping YAML path"
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)

    if args.issue:
        return _run_issue(args)
    if args.barrier is not None:
        return _run_barrier(args)
    return _run_check(args)


if __name__ == "__main__":
    sys.exit(main())
