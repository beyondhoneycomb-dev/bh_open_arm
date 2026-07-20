"""Single entry point for the CI rule set of `06` §5.

Exit status is the contract: non-zero when any judged rule reports a finding.
`06` §5 admits no warning level, so there is no partial success — a run is green
or the build fails.

Usage:
    python -m registry.check                 # judge range, CI-01..CI-17
    python -m registry.check --all           # build range, CI-01..CI-18
    python -m registry.check --rule CI-05e   # one rule
    python -m registry.check --json          # machine-readable report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from registry.checks import BUILD_RANGE, JUDGE_EXCLUDED, JUDGE_RANGE, module_for
from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult

EXIT_OK = 0
EXIT_VIOLATIONS = 1

_JUDGE_RANGE_LABEL = "CI-01..CI-17"
_BUILD_RANGE_LABEL = "CI-01..CI-18"


def run_rules(corpus: Corpus, modules: tuple[ModuleType, ...]) -> list[RuleResult]:
    """Execute a set of rules against a corpus.

    `CI-18` needs the judged findings total, because its predicate cites the band
    acceptance gate. It is passed the count from the rules that ran before it in
    this same invocation.

    Args:
        corpus: The corpus under test.
        modules: Rule executables to run, in order.

    Returns:
        (list[RuleResult]) One result per rule, in the given order.
    """
    results: list[RuleResult] = []
    for module in modules:
        if module.RULE_ID in JUDGE_EXCLUDED:
            judged = sum(
                len(result.findings) for result in results if result.rule_id not in JUDGE_EXCLUDED
            )
            results.append(module.run(corpus, judged))
        else:
            results.append(module.run(corpus))
    return results


def as_report(results: list[RuleResult], judged_only: bool) -> dict[str, Any]:
    """Assemble the machine-readable report.

    Args:
        results: Rule results.
        judged_only: Whether the run covered the judge range only.

    Returns:
        (dict[str, Any]) Report with per-rule results and a verdict.
    """
    judged = [r for r in results if r.rule_id not in JUDGE_EXCLUDED]
    return {
        "range": _JUDGE_RANGE_LABEL if judged_only else _BUILD_RANGE_LABEL,
        "rules_run": len(results),
        "findings_total": sum(len(r.findings) for r in results),
        "judged_findings_total": sum(len(r.findings) for r in judged),
        "green": all(r.passed for r in judged),
        "rules": [
            {
                "rule_id": r.rule_id,
                "sites": r.sites,
                "vacuous": r.vacuous,
                "findings": [f.as_dict() for f in r.findings],
                "notes": list(r.notes),
            }
            for r in results
        ],
    }


def print_text(results: list[RuleResult]) -> None:
    """Print a terminal summary of a run.

    Args:
        results: Rule results.
    """
    for result in results:
        if result.passed:
            state = "VACUOUS" if result.vacuous else "green"
            print(f"{result.rule_id:<8} {state:<8} sites={result.sites}")
        else:
            print(
                f"{result.rule_id:<8} {'FAIL':<8} sites={result.sites} "
                f"findings={len(result.findings)}"
            )
        for finding in result.findings:
            print(f"    {finding.as_line()}")
        for note in result.notes:
            print(f"    note: {note}")


def main(argv: list[str] | None = None) -> int:
    """Run the rule set and report.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        (int) Process exit status; non-zero when a judged rule found a violation.
    """
    parser = argparse.ArgumentParser(prog="oa-check", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"run the build range {_BUILD_RANGE_LABEL} instead of {_JUDGE_RANGE_LABEL}",
    )
    parser.add_argument("--rule", action="append", default=None, help="run only this rule id")
    parser.add_argument("--json", action="store_true", help="emit the machine-readable report")
    args = parser.parse_args(argv)

    corpus = Corpus(args.root)
    if args.rule:
        modules = tuple(module_for(rule_id) for rule_id in args.rule)
        judged_only = False
    else:
        modules = BUILD_RANGE if args.all else JUDGE_RANGE
        judged_only = not args.all

    results = run_rules(corpus, modules)
    report = as_report(results, judged_only)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(results)
        print(
            f"\n{report['range']}: {report['rules_run']} rules, "
            f"{report['judged_findings_total']} judged finding(s) — "
            f"{'GREEN' if report['green'] else 'BUILD FAILED'}"
        )

    return EXIT_OK if report["green"] else EXIT_VIOLATIONS


if __name__ == "__main__":
    sys.exit(main())
