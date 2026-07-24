"""CG-4B-05c — the pin is a commit SHA and the ghost version appears nowhere operative.

The ghost literal is read from `deps.phantom.PHANTOM_VERSION` so this test file, too,
never writes it — the single source stays `deps/phantom.py`. `deps/lerobot.pin` is the
one documented exception: its `self_claimed_version` names the ghost on purpose so the
pin can assert the mismatch is intended.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.compat.contract_regression import ghost_version
from deps import phantom

REPO_ROOT = Path(__file__).resolve().parents[2]

# Operative locations that decide what installs or what this band registers. The pin
# file is excluded — it documents the ghost by design (see module docstring).
OPERATIVE_SCAN_ROOTS = (
    REPO_ROOT / "backend" / "compat" / "contract_regression",
    REPO_ROOT / "pyproject.toml",
    REPO_ROOT / "uv.lock",
)


def test_pin_is_a_commit_sha_resolving_to_the_released_version() -> None:
    verdict = ghost_version.check_ghost_version()
    assert verdict.ok, verdict.as_line()
    assert re.fullmatch(r"[0-9a-f]{40}", verdict.commit_sha)
    assert verdict.resolved_version == phantom.RESOLVED_VERSION
    assert verdict.resolved_version != phantom.PHANTOM_VERSION


def test_ghost_literal_absent_from_every_operative_location() -> None:
    offenders = []
    for root in OPERATIVE_SCAN_ROOTS:
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
                continue
            if phantom.PHANTOM_VERSION in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"ghost version found in operative files: {offenders}"


def test_a_ghost_semver_spec_is_refused_by_the_grammar() -> None:
    # The pin discipline this check reuses: a ghost semver spec is rejected as a
    # phantom, while a SHA checkout form is allowed.
    ghost_spec = f"lerobot=={phantom.PHANTOM_VERSION}"
    rejection = phantom.reject_spec(ghost_spec)
    assert rejection is not None
    assert rejection.reason == phantom.REASON_PHANTOM

    sha_spec = "lerobot @ git+https://github.com/huggingface/lerobot@30da8e687a6dfc617fcd94afc367ac7071c376ce"
    assert phantom.reject_spec(sha_spec) is None


def test_pin_file_documents_the_ghost_only_as_provenance() -> None:
    # The one place the ghost may appear is the pin's self-claimed-version field, and
    # deps.pin must bless the mismatch as intended — otherwise it would be a real spec.
    from deps import pin

    report = pin.validate_pin(pin.load_pin(REPO_ROOT / "deps" / "lerobot.pin"))
    assert report.ok
    assert report.self_claimed_version == phantom.PHANTOM_VERSION
    assert report.resolved_version == phantom.RESOLVED_VERSION
