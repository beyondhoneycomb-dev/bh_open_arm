"""Locations of the versioned planning corpus, relative and absolute.

`CORPUS_VERSION` is the single declaration of the version segment. A dozen call
sites, the `spine_ref` pattern in `registry/schema/traceability.schema.json`, and
CI-17's plan-path regex all assert the same prefix; resolving every one of them
from here is what makes them move together when the corpus is re-versioned. A
prefix duplicated across modules and a JSON schema still compiles and type-checks
after one copy diverges, so nothing but a shared constant can fail them together.

These live in the package root rather than a `registry/paths.py` because `06`
§3.2 and `02a` declare ownership per path: a new module would be a file no
`owns[]` glob claims, and CI-02b rejects that. `registry/__init__.py` is already
declared owned by the work package that owns the seeder.

Two shapes are published because callers need both. `*_SUBPATH` is relative and
is what anything taking a repository root as an argument must use — the checkers
and the normalization validator are handed a root (a real repo, or a doctored
tree a test built) and must never reach for this package's own root. `*_DIR` is
anchored at this repository and is for the tools that only ever run against it.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CORPUS_VERSION = "v1"

DOCS_SUBPATH = Path("docs") / CORPUS_VERSION
PLAN_SUBPATH = DOCS_SUBPATH / "plan"
SPEC_SUBPATH = DOCS_SUBPATH / "spec"
NORMALIZATION_SUBPATH = PLAN_SUBPATH / "normalization"

DOCS_ROOT = REPO_ROOT / DOCS_SUBPATH
PLAN_DIR = REPO_ROOT / PLAN_SUBPATH
SPEC_DIR = REPO_ROOT / SPEC_SUBPATH
NORMALIZATION_DIR = REPO_ROOT / NORMALIZATION_SUBPATH

# Registry fields, manifest fields and report text carry repo-relative POSIX
# strings rather than filesystem paths; the schema pattern and CI-17 match on
# these, so they are derived from the subpaths above and never written twice.
PLAN_DIR_REL = PLAN_SUBPATH.as_posix()
SPEC_DIR_REL = SPEC_SUBPATH.as_posix()

SPINE_DOC_NAME = "00-실행계획-개요.md"
SPINE_DOC_REL = f"{PLAN_DIR_REL}/{SPINE_DOC_NAME}"

DAG_DOC_NAME = "01-의존성-DAG-및-병렬화.md"
DAG_DOC_REL = f"{PLAN_DIR_REL}/{DAG_DOC_NAME}"
