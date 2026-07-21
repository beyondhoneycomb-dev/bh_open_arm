"""Load and validate the gate ID namespace mapping against the live corpus.

The mapping (`docs/plan/normalization/gate_spec_map.yaml`) is the `WP-N1-03`
deliverable: it binds every plan-owned `PG-*` gate to the specification ids and
document sections that justify it, without reusing a spec id as a gate id.

Schema validity proves shape. This module proves the mapping tells the truth
about the corpus:

* the mapped gate set equals the `03` gate roster exactly — no gate is left
  unmapped and no row names a gate the roster does not declare, so a renamed or
  dropped gate cannot hide;
* every `spec_ref` resolves to a real definition — an `FR-*`/`NFR-*` declared in
  a `docs/spec` requirement table, a `D-n`/`M-n` defined in `docs/spec/16`, or a
  `NN §S` section that exists in document `NN`. This is the "no dangling
  reference" contract (02a §1.5 WP-N1-03 ②): the ghost id `M-25` and any other
  cited-but-undefined id fail here.

A mapping that passes schema but fails here would be green while pointing at gates
and ids that do not exist — the "green but catching nothing" outcome 02a §-2.3
names the worst.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from registry.normalization.validator import Corpus, section_body

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(__file__).resolve().parent / "gate_map.schema.json"
GATE_MAP_PATH = REPO_ROOT / "docs" / "plan" / "normalization" / "gate_spec_map.yaml"

_FR_NFR = re.compile(r"^(?:FR|NFR)-[A-Z]{2,4}-\d{3}$")
_DM = re.compile(r"^[DM]-\d+$")
_SECTION_REF = re.compile(r"^(\d{2}) §(\d+(?:\.\d+)*[a-z]?)$")


@dataclass(frozen=True)
class Violation:
    """One mapping claim the corpus does not support.

    Attributes:
        pg_id: The gate row the violation belongs to, or `(coverage)` for a
            roster mismatch that is not tied to a single row.
        kind: Which class of claim failed (coverage, duplicate, spec_ref).
        detail: What was asserted and what the corpus actually holds.
    """

    pg_id: str
    kind: str
    detail: str

    def as_line(self) -> str:
        """Render the violation as one report line.

        Returns:
            (str) Single-line human-readable form.
        """
        return f"{self.pg_id} [{self.kind}] {self.detail}"


def load_gate_map(path: Path) -> dict[str, Any]:
    """Parse a gate mapping document from YAML.

    Args:
        path: Path to a gate mapping YAML file.

    Returns:
        (dict[str, Any]) The parsed document.

    Raises:
        TypeError: When the file does not parse to a mapping.
    """
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} did not parse to a mapping")
    return loaded


def load_schema() -> dict[str, Any]:
    """Load the gate mapping JSON Schema.

    Returns:
        (dict[str, Any]) The parsed schema document.
    """
    parsed: Any = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(f"{SCHEMA_PATH} did not parse to a mapping")
    return parsed


def schema_errors(document: dict[str, Any]) -> list[str]:
    """Return the schema violations of a gate mapping document, in document order.

    Args:
        document: A parsed gate mapping document.

    Returns:
        (list[str]) One message per violation; empty when the document is valid.
    """
    validator = Draft202012Validator(load_schema())
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '(root)'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda error: error.absolute_path)
    ]


def _ref_resolves(corpus: Corpus, ref: str) -> bool:
    """Return whether a `spec_ref` resolves to a real corpus definition.

    A `D-n`/`M-n` counts as resolved when it has at least one definition row:
    the map's contract is "not dangling", not "defined exactly once", so an id
    like `M-22` that the specification defines in two tables still resolves.

    Args:
        corpus: The corpus facts.
        ref: A spec reference string.

    Returns:
        (bool) True when the reference exists in the corpus.
    """
    if _FR_NFR.match(ref):
        return ref in corpus.spec_requirements
    if _DM.match(ref):
        return corpus.dm_definition_count(ref) >= 1
    section = _SECTION_REF.match(ref)
    if section:
        path = corpus.spec_file(section.group(1))
        return path is not None and section_body(path, section.group(2)) is not None
    return False


def _coverage_violations(corpus: Corpus, rows: list[dict[str, Any]]) -> list[Violation]:
    """Report gates the mapping fails to cover exactly once.

    Args:
        corpus: The corpus facts.
        rows: The mapping rows.

    Returns:
        (list[Violation]) Missing gates, extra gates, and duplicate rows.
    """
    declared = [str(row.get("pg_id", "")) for row in rows]
    seen: set[str] = set()
    violations: list[Violation] = []
    for pg_id in declared:
        if pg_id in seen:
            violations.append(Violation(pg_id, "duplicate", "gate mapped more than once"))
        seen.add(pg_id)
    for missing in sorted(corpus.gate_roster - seen):
        violations.append(Violation(missing, "coverage", "03 gate roster gate has no mapping row"))
    for extra in sorted(seen - corpus.gate_roster):
        violations.append(Violation(extra, "coverage", "mapped gate is not in the 03 gate roster"))
    return violations


def validate(corpus: Corpus, document: dict[str, Any]) -> list[Violation]:
    """Validate a schema-valid gate mapping document against the corpus.

    Args:
        corpus: The corpus facts.
        document: A mapping document that has already passed schema validation.

    Returns:
        (list[Violation]) Every unsupported claim, in document order.
    """
    rows = list(document.get("rows", []))
    violations = _coverage_violations(corpus, rows)
    for row in rows:
        pg_id = str(row.get("pg_id", "?"))
        for ref in row.get("spec_refs", []):
            if not _ref_resolves(corpus, str(ref)):
                violations.append(
                    Violation(pg_id, "spec_ref", f"{ref} resolves to no corpus definition")
                )
    return violations
