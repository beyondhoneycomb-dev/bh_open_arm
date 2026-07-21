"""Pre-merge ownership-diff gate (WP-ENV-03 acceptance ⑥).

`05` §2.1: "a modification outside the declared paths does not merge." A branch
implementing WP-X may touch only WP-X's `owns[]` tree; a diff reaching into another
package's EXCLUSIVE tree is refused, and a diff that stays inside is NOT over-blocked.

The core `check_diff` is pure — it takes the ownership map as data, so it is tested
against hand-built maps without importing the registry. `load_ownership` reads the
committed registry for the real run; `main` wires the two for CI.

This lives under `.github/` (owned by WP-ENV-03) and inserts the repository root on
`sys.path` so it can reuse `registry.checks.globs` when run as a bare script.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import yaml  # noqa: E402 — after the sys.path insert so registry.* also resolves

from registry.checks.globs import matches_any, split_globs  # noqa: E402

MODE_EXCLUSIVE = "EXCLUSIVE"

# Owned by no work package — repository furniture any branch may touch. `.github`
# is intentionally NOT here: WP-ENV-03 owns it, so a foreign branch touching it is a
# real intrusion the map already catches.
FURNITURE_FILES = frozenset({"README.md", "LICENSE", ".gitignore"})
FURNITURE_PREFIXES = ("docs/", ".git/", "registry/build/")


@dataclass(frozen=True)
class DiffVerdict:
    """The outcome of judging one diff against the declared owner.

    Attributes:
        declaring_wp: The work package the branch claims to implement.
        blocked: True when the diff is refused merge.
        violations: `(path, reason)` for each offending path.
    """

    declaring_wp: str
    blocked: bool
    violations: tuple[tuple[str, str], ...]

    def as_lines(self) -> list[str]:
        """Render the verdict as report lines.

        Returns:
            (list[str]) One header line plus one line per violation.
        """
        if not self.blocked:
            return [f"{self.declaring_wp}: ownership diff CLEARED"]
        head = f"{self.declaring_wp}: ownership diff BLOCKED ({len(self.violations)} path(s))"
        return [head, *[f"  {path} — {reason}" for path, reason in self.violations]]


def _is_furniture(path: str) -> bool:
    """Report whether a path is unowned repository furniture."""
    return path in FURNITURE_FILES or path.startswith(FURNITURE_PREFIXES)


def check_diff(
    declaring_wp: str,
    changed_paths: tuple[str, ...],
    ownership: dict[str, tuple[str, ...]],
) -> DiffVerdict:
    """Judge whether a diff stays within the declared owner's tree.

    A path is refused when it lands in another package's EXCLUSIVE tree, or when it
    is owned by nobody and is not furniture. A path inside the declaring package's
    own globs is always allowed — that is the non-over-block half.

    Args:
        declaring_wp: The work package the branch implements.
        changed_paths: Root-relative POSIX paths the diff touches.
        ownership: `WP-*` to its EXCLUSIVE globs.

    Returns:
        (DiffVerdict) Blocked with per-path reasons, or cleared.
    """
    own_globs = ownership.get(declaring_wp, ())
    violations: list[tuple[str, str]] = []
    for path in changed_paths:
        if matches_any(path, own_globs):
            continue
        intruded = sorted(
            wp for wp, globs in ownership.items() if wp != declaring_wp and matches_any(path, globs)
        )
        if intruded:
            violations.append((path, f"intrudes on EXCLUSIVE tree of {', '.join(intruded)}"))
        elif not _is_furniture(path):
            violations.append((path, "outside the declared owns[] and owned by no work package"))
    return DiffVerdict(declaring_wp, bool(violations), tuple(violations))


def load_ownership(registry_path: Path) -> dict[str, tuple[str, ...]]:
    """Read the EXCLUSIVE ownership globs of every work package from the registry.

    Args:
        registry_path: Path to `registry/traceability.yaml`.

    Returns:
        (dict[str, tuple[str, ...]]) `WP-*` to its EXCLUSIVE globs.
    """
    document = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    claims: dict[str, set[str]] = {}
    for entry in document.get("entries", []):
        wp = entry.get("wp")
        if not isinstance(wp, str) or not wp.startswith("WP-"):
            continue
        owned = list(entry.get("owns", []) or [])
        for phase in entry.get("phases", []) or []:
            owned.extend(phase.get("owns", []) or [])
        for own in owned:
            if own.get("mode") == MODE_EXCLUSIVE:
                claims.setdefault(wp, set()).update(split_globs(str(own.get("glob", ""))))
    return {wp: tuple(sorted(globs)) for wp, globs in claims.items()}


def main(argv: list[str] | None = None) -> int:
    """Judge a diff read from `--wp` and `--changed`/stdin against the registry.

    Args:
        argv: Command-line arguments.

    Returns:
        (int) Non-zero when the diff is blocked.
    """
    parser = argparse.ArgumentParser(prog="ownership-diff", description=__doc__)
    parser.add_argument("--wp", required=True, help="the WP-* the branch implements")
    parser.add_argument(
        "--registry",
        type=Path,
        default=_REPO_ROOT / "registry" / "traceability.yaml",
        help="traceability registry path",
    )
    parser.add_argument(
        "--changed",
        nargs="*",
        default=None,
        help="changed paths; when omitted, read one per line from stdin",
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable verdict")
    args = parser.parse_args(argv)

    changed = (
        args.changed
        if args.changed is not None
        else [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    )
    ownership = load_ownership(args.registry)
    verdict = check_diff(args.wp, tuple(changed), ownership)

    if args.json:
        print(
            json.dumps(
                {
                    "wp": verdict.declaring_wp,
                    "blocked": verdict.blocked,
                    "violations": [{"path": p, "reason": r} for p, r in verdict.violations],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for line in verdict.as_lines():
            print(line, file=sys.stderr if verdict.blocked else sys.stdout)
    return 1 if verdict.blocked else 0


if __name__ == "__main__":
    sys.exit(main())
