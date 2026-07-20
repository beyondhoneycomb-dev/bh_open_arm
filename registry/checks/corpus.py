"""The corpus a CI run judges: registry, plan catalogue, spec, manifests, tree.

Every checker reads this one object so that "the corpus" means the same thing to
all of them. Substrates are loaded lazily and cached, because a run of a single
rule should not pay for parsing 17 spec documents it never looks at.

Ownership: a `Corpus` is read-only for checkers. Nothing under `registry/checks/`
writes to the paths it describes.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

from registry.ingest.catalog import CatalogEntry
from registry.ingest.catalog import parse_all as parse_catalogs
from registry.ingest.markdown import all_tables, plain_text, read_sections
from registry.ingest.spec import parse_all as parse_spec

WP_NOT_A_WORK_PACKAGE = frozenset({"OUT", "DEFERRED"})

CATALOG_FILES = (
    "02a-작업패키지-Wave-minus1-to-1.md",
    "02b-작업패키지-Wave-2-3.md",
    "02c-작업패키지-Wave-4-5.md",
    "02d-작업패키지-GUI.md",
)

GATE_DOC = "03-측정-게이트.md"

# `06` §5 CI-02b names these exactly: they are canon documents and repository
# furniture, not the output tree of any work package, so they cannot be orphans.
NON_ARTIFACT_PREFIXES = ("docs/", ".git/", ".github/", "registry/build/")
NON_ARTIFACT_FILES = ("README.md", "LICENSE", ".gitignore")

_MANIFEST_SUFFIXES = (".yaml", ".yml", ".json")

_SPEC_DOC_NUMBER = re.compile(r"^(\d{2})-")
_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*[a-z]?)(?:\s|$)")


@dataclass(frozen=True)
class GateCell:
    """One gate identifier read from a declaration site, with its provenance.

    A "declaration site" is a place where a gate id arrives as a *field value*:
    a gate-table ID cell, a manifest `gates:`-family value, or a registry gate
    axis value. Prose that merely mentions a gate id is not a site, and `06` §5
    (CI-10, CI-11b) makes that distinction load-bearing — a lexical sweep over
    `docs/plan/**` detonates on the very sentences that document the bans.

    Attributes:
        value: The identifier exactly as written in the field.
        path: File the value came from.
        line: 1-indexed line, or 0 when the substrate carries no line number.
        site: Which declaration site kind produced it.
        owner: The `WP-*` or `req` the site belongs to, for attribution.
    """

    value: str
    path: str
    line: int
    site: str
    owner: str

    def location(self) -> str:
        """Render the provenance as a report `path` value.

        Returns:
            (str) `<file>:<line>` when a line is known, else `<file>`.
        """
        return f"{self.path}:{self.line}" if self.line else self.path


@dataclass
class Corpus:
    """Everything a CI run reads, resolved from one repository root.

    Attributes:
        root: Repository root; every reported path is relative to it.
        registry_path: Location of `traceability.yaml`.
        plan_dir: Directory holding the planning documents.
        spec_dir: Directory holding the specification documents.
        manifest_dir: Directory the WP manifests are expected in.
    """

    root: Path
    registry_path: Path = field(init=False)
    plan_dir: Path = field(init=False)
    spec_dir: Path = field(init=False)
    manifest_dir: Path = field(init=False)

    def __init__(
        self,
        root: Path,
        registry_path: Path | None = None,
        plan_dir: Path | None = None,
        spec_dir: Path | None = None,
        manifest_dir: Path | None = None,
    ) -> None:
        """Resolve the corpus substrates against a repository root.

        Args:
            root: Repository root.
            registry_path: Override for `registry/traceability.yaml`.
            plan_dir: Override for `docs/plan`.
            spec_dir: Override for `docs/spec`.
            manifest_dir: Override for `registry/build/manifests`.
        """
        self.root = root
        self.registry_path = registry_path or root / "registry" / "traceability.yaml"
        self.plan_dir = plan_dir or root / "docs" / "plan"
        self.spec_dir = spec_dir or root / "docs" / "spec"
        self.manifest_dir = manifest_dir or root / "registry" / "build" / "manifests"

    def rel(self, path: Path) -> str:
        """Express a path relative to the repository root when possible.

        Args:
            path: Absolute or relative path.

        Returns:
            (str) Root-relative POSIX path, or the original string form.
        """
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    @cached_property
    def registry(self) -> dict[str, Any]:
        """Load the traceability registry document.

        Returns:
            (dict[str, Any]) Parsed YAML with `version`, `spine_ref`, `entries`.
        """
        loaded: Any = yaml.safe_load(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise TypeError(f"{self.registry_path} did not parse to a mapping")
        return loaded

    @cached_property
    def entries(self) -> tuple[dict[str, Any], ...]:
        """Return every registry record.

        Returns:
            (tuple[dict[str, Any], ...]) Records in file order.
        """
        raw = self.registry.get("entries", [])
        if not isinstance(raw, list):
            raise TypeError("registry 'entries' is not a list")
        return tuple(raw)

    @cached_property
    def work_entries(self) -> tuple[dict[str, Any], ...]:
        """Return records whose `wp` names an actual work package.

        `OUT` and `DEFERRED` are not work packages, so rules that judge work
        (CI-04, CI-07 and friends) must not see them. The registry currently
        carries hundreds of `DEFERRED` records; a rule that forgets this exemption
        reports its false failures by the hundred.

        Returns:
            (tuple[dict[str, Any], ...]) Records with a real `wp`.
        """
        return tuple(e for e in self.entries if e.get("wp") not in WP_NOT_A_WORK_PACKAGE)

    @cached_property
    def by_wp(self) -> dict[str, tuple[dict[str, Any], ...]]:
        """Group work-package records by `wp`.

        Records are keyed by requirement, so one work package owns many records.

        Returns:
            (dict[str, tuple[dict[str, Any], ...]]) `WP-*` to its records.
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        for entry in self.work_entries:
            grouped.setdefault(str(entry["wp"]), []).append(entry)
        return {wp: tuple(records) for wp, records in grouped.items()}

    @cached_property
    def catalog(self) -> dict[str, CatalogEntry]:
        """Parse the work-package catalogues `02a`–`02d`.

        The catalogues issue work-package ids and own shape assignment; the
        registry only registers what they issued.

        Returns:
            (dict[str, CatalogEntry]) `WP-*` to its catalogue row.
        """
        return {entry.wp_id: entry for entry in parse_catalogs(self.plan_dir)}

    @cached_property
    def catalog_paths(self) -> tuple[Path, ...]:
        """Return the catalogue files that actually exist.

        CI-05b fails closed when a catalogue is missing: if the checker looked for
        a single `02-작업패키지.md` it would find nothing and judge every `spawns`
        a phantom, so the search space is the four real files.

        Returns:
            (tuple[Path, ...]) Existing catalogue paths.
        """
        return tuple(p for p in (self.plan_dir / name for name in CATALOG_FILES) if p.is_file())

    @cached_property
    def plan_paths(self) -> tuple[Path, ...]:
        """Return every planning document.

        Returns:
            (tuple[Path, ...]) Sorted `docs/plan/*.md`.
        """
        return tuple(sorted(self.plan_dir.glob("*.md")))

    @cached_property
    def spec_requirements(self) -> frozenset[str]:
        """Return requirement ids declared in specification tables.

        Declaration tables, not a lexical sweep: the literal `06` §5 CI-01 regex
        also harvests ids that appear only in prose explaining the id format, and
        those requirements do not exist. CI-01 reports that gap rather than
        inheriting it.

        Returns:
            (frozenset[str]) Declared `FR-*`/`NFR-*` ids.
        """
        return frozenset(req.req_id for req in parse_spec(self.spec_dir))

    @cached_property
    def spec_sections(self) -> dict[str, frozenset[str]]:
        """Map each spec document number to the section numbers it defines.

        Returns:
            (dict[str, frozenset[str]]) Document number to section numbers.
        """
        return _section_index(self.spec_dir)

    @cached_property
    def plan_sections(self) -> dict[str, frozenset[str]]:
        """Map each planning document number to the section numbers it defines.

        Returns:
            (dict[str, frozenset[str]]) Document number to section numbers.
        """
        return _section_index(self.plan_dir)

    @cached_property
    def manifests(self) -> dict[str, dict[str, Any]]:
        """Load WP manifests, if `WP-BOOT-02` has produced any.

        No planning document fixes a storage path for manifests, so this reads the
        one generated tree `WP-BOOT-02` owns. An empty result is reported as an
        empty corpus slice, never as a rule violation — `06` §5 defines no rule
        requiring manifests to exist, and inventing one would be adding a check
        that `06` §5 does not contain.

        Returns:
            (dict[str, dict[str, Any]]) `wp_id` to manifest body.
        """
        if not self.manifest_dir.is_dir():
            return {}
        found: dict[str, dict[str, Any]] = {}
        for path in sorted(self.manifest_dir.rglob("*")):
            if path.suffix not in _MANIFEST_SUFFIXES or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            body: Any = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
            if not isinstance(body, dict):
                continue
            found[str(body.get("wp_id", path.stem))] = body
        return found

    @cached_property
    def gate_roster(self) -> frozenset[str]:
        """Return the `PG-*` gates document `03` actually declares.

        Read from the ID column of the gate table, not by regex over the document,
        for the same reason CI-10 and CI-11b parse fields: `03` discusses gate ids
        it does not declare.

        Returns:
            (frozenset[str]) Declared `PG-*` ids.
        """
        return frozenset(cell.value for cell in self.gate_table_cells)

    @cached_property
    def gate_table_cells(self) -> tuple[GateCell, ...]:
        """Extract gate ids from the ID column of the `03` gate table.

        Returns:
            (tuple[GateCell, ...]) One cell per gate-table row.
        """
        path = self.plan_dir / GATE_DOC
        if not path.is_file():
            return ()
        cells: list[GateCell] = []
        for table in all_tables(path):
            if not table.header or plain_text(table.header[0]) != "ID":
                continue
            for offset, row in enumerate(table.rows, start=1):
                value = plain_text(row[0]).lstrip("🔴 ").strip()
                if not value:
                    continue
                cells.append(
                    GateCell(
                        value=value,
                        path=self.rel(path),
                        line=table.header_line + 1 + offset,
                        site="gate-table-id-cell",
                        owner=value,
                    )
                )
        return tuple(cells)

    @cached_property
    def registry_gate_cells(self) -> tuple[GateCell, ...]:
        """Extract every gate id occupying a gate-axis slot in the registry.

        The gate axis is `gate[]`, the gate position of `stale_on[]` entries, and
        `negative_branch[].gate`. Prose inside `negative_branch[].action` is not an
        axis value and is deliberately not read.

        Returns:
            (tuple[GateCell, ...]) Gate-axis values with provenance.
        """
        rel = self.rel(self.registry_path)
        cells: list[GateCell] = []
        for entry in self.entries:
            owner = f"{entry.get('req', '?')}/{entry.get('wp', '?')}"
            for value in entry.get("gate", []) or []:
                cells.append(GateCell(str(value), rel, 0, "registry-gate-axis", owner))
            for branch in entry.get("negative_branch", []) or []:
                gate = branch.get("gate")
                if gate:
                    cells.append(
                        GateCell(str(gate), rel, 0, "registry-negative-branch-gate", owner)
                    )
            for trigger in entry.get("stale_on", []) or []:
                head = str(trigger).split(":", 1)[0]
                if head.startswith(("PG-", "CG-", "M-")):
                    cells.append(GateCell(head, rel, 0, "registry-stale-on-gate", owner))
        return tuple(cells)

    @cached_property
    def manifest_gate_cells(self) -> tuple[GateCell, ...]:
        """Extract gate ids from manifest `gates:`-family field values.

        Returns:
            (tuple[GateCell, ...]) Gate values declared by manifests.
        """
        cells: list[GateCell] = []
        for wp_id, body in sorted(self.manifests.items()):
            for key in ("gates", "exit_gates", "requires_gates"):
                for value in body.get(key, []) or []:
                    cells.append(
                        GateCell(
                            value=str(value),
                            path=f"{self.rel(self.manifest_dir)}/{wp_id}",
                            line=0,
                            site=f"manifest-{key}",
                            owner=wp_id,
                        )
                    )
        return tuple(cells)

    @cached_property
    def gate_declaration_sites(self) -> tuple[GateCell, ...]:
        """Return every place a gate id arrives as a field value.

        This is the exact scope CI-10 and CI-11b are allowed to police.

        Returns:
            (tuple[GateCell, ...]) All declaration-site gate values.
        """
        return self.gate_table_cells + self.manifest_gate_cells + self.registry_gate_cells

    @cached_property
    def tracked_files(self) -> tuple[str, ...]:
        """List repository files that are neither ignored nor absent.

        Uses git so that the ignore rules have exactly one definition. Files that
        are untracked but not ignored count: work packages produce files before
        anyone commits them.

        Returns:
            (tuple[str, ...]) Root-relative POSIX paths.
        """
        # core.quotePath=false keeps the Korean document names as literal UTF-8;
        # git's default octal-escaped quoting turns every one of them into a
        # distinct string that no path prefix will ever match.
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        )
        return tuple(sorted(line for line in result.stdout.splitlines() if line.strip()))

    @cached_property
    def artifact_tree(self) -> tuple[str, ...]:
        """List files that belong to some work package's output tree.

        Returns:
            (tuple[str, ...]) Candidate files for orphan analysis.
        """
        return tuple(
            path
            for path in self.tracked_files
            if not path.startswith(NON_ARTIFACT_PREFIXES) and path not in NON_ARTIFACT_FILES
        )


def _section_index(directory: Path) -> dict[str, frozenset[str]]:
    """Build a document-number to section-identifier index for a directory.

    A section is addressable by its number when it has one (`3.1`) and by its full
    heading text either way. Both forms are indexed because the specification
    numbers only some of its headings — `docs/spec/14` labels several with letters
    (`D. 실패 감지·복구`) — and a `spec_ref` naming one of those points at a real
    section that a number-only index would call missing.

    Args:
        directory: Directory of numbered Markdown documents.

    Returns:
        (dict[str, frozenset[str]]) Document number to addressable section ids.
    """
    index: dict[str, set[str]] = {}
    if not directory.is_dir():
        return {}
    for path in sorted(directory.glob("*.md")):
        match = _SPEC_DOC_NUMBER.match(path.name)
        if not match:
            continue
        identifiers = index.setdefault(match.group(1), set())
        for section in read_sections(path):
            heading = section.title.lstrip("#").strip()
            if not heading:
                continue
            identifiers.add(heading)
            number = _SECTION_NUMBER.match(heading)
            if number:
                identifiers.add(number.group(1))
    return {doc: frozenset(values) for doc, values in index.items()}
