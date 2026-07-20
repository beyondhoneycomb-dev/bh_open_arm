"""CI-16 — graph cross-check: declared `downstream[]` against the real reference graph.

`06` §5.6 calls this the only check that offsets the cost of the registry being a
"second truth". Two directions fail: a real reference that `downstream[]` omits,
and a declared edge with no reference behind it. The second is recoverable — `06`
§2.2 lets a package declare `justification` for an edge a static graph cannot see,
such as a runtime dynamic load.

The coverage limit is structural and `06` §5.6 states it rather than hiding it: a
static graph cannot see a frontend consuming a WS envelope by string key, a udev
rule joined to a profile only through YAML, or a dataset schema tied to training
normalisation statistics. That gap is offset by `CONTRACT_FROZEN` plus CI-09, and
the remainder is caught by a gate or by nobody.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from registry.checks.corpus import Corpus
from registry.checks.globs import expand, split_globs
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-16"
TITLE = "graph cross-check"

PYTHON_SUFFIX = ".py"


def _module_name(path: str) -> str:
    """Convert a repository path to its dotted Python module name.

    Args:
        path: Root-relative POSIX path.

    Returns:
        (str) Dotted module name.
    """
    stem = path[: -len(PYTHON_SUFFIX)]
    parts = [part for part in stem.split("/") if part]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def import_graph(corpus: Corpus) -> dict[str, set[str]]:
    """Build a module-level import graph over the repository's Python sources.

    Args:
        corpus: The corpus under test.

    Returns:
        (dict[str, set[str]]) Module name to the modules it imports.
    """
    graph: dict[str, set[str]] = defaultdict(set)
    for path in corpus.tracked_files:
        if not path.endswith(PYTHON_SUFFIX):
            continue
        source = Path(corpus.root / path)
        if not source.is_file():
            continue
        try:
            tree = ast.parse(source.read_text(encoding="utf-8", errors="replace"), filename=path)
        except SyntaxError:
            continue
        importer = _module_name(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                graph[importer].update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                graph[importer].add(node.module)
    return graph


def run(corpus: Corpus) -> RuleResult:
    """Report declared downstream edges with no reference and no justification.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per unbacked declared edge.
    """
    graph = import_graph(corpus)

    owned_modules: dict[str, set[str]] = {}
    for wp_id, records in corpus.by_wp.items():
        globs: set[str] = set()
        for record in records:
            owned = list(record.get("owns", []) or [])
            for phase in record.get("phases", []) or []:
                owned.extend(phase.get("owns", []) or [])
            for entry in owned:
                globs.update(split_globs(str(entry.get("glob", ""))))
        files = expand(tuple(sorted(globs)), corpus.tracked_files)
        owned_modules[wp_id] = {
            _module_name(path) for path in files if path.endswith(PYTHON_SUFFIX)
        }

    findings = []
    sites = 0

    for wp_id, records in sorted(corpus.by_wp.items()):
        source_modules = owned_modules.get(wp_id, set())
        if not source_modules:
            continue
        justified = any(str(record.get("justification", "") or "").strip() for record in records)
        declared = {
            str(target)
            for record in records
            for target in record.get("downstream", []) or []
            if str(target).startswith("WP-")
        }
        for target in sorted(declared):
            target_modules = owned_modules.get(target, set())
            if not target_modules:
                continue
            sites += 1
            referenced = any(
                any(imported.startswith(source) for source in source_modules)
                for module in target_modules
                for imported in graph.get(module, set())
            )
            if referenced or justified:
                continue
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=f"{wp_id} -> {target}",
                    path=corpus.rel(corpus.registry_path),
                    reason=(
                        "downstream edge is declared but the static reference graph shows no "
                        "reference, and no justification records why it cannot be seen"
                    ),
                    expected=f"an import from {target}'s modules, or a justification field",
                    actual="no reference found, justification absent",
                )
            )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=sites,
        vacuous=not sites,
        notes=(
            (
                "coverage is structurally incomplete: string-keyed, YAML-joined and "
                "statistics-joined dependencies are invisible to a static graph (06 §5.6).",
            )
        ),
    )
