"""WP-0A-02's manifest declares the env hash and clears the start barrier.

WP-0A-02 is downstream of WP-ENV-04, so its manifest must declare the issued
`env_hash`; a manifest that declares none, or a superseded one, is refused start
(02a WP-ENV-04, registry/env/barrier.py). This checks the wiring end to end: the
manifest built from the seeded registry carries the issued hash and clears the
barrier, while a manifest lacking it is blocked.
"""

from __future__ import annotations

from registry.env.barrier import REASON_ABSENT, check_manifest
from registry.env.env_hash import read_issued
from registry.generate.manifests import build_manifest
from registry.generate.source import REGISTRY_PATH, group_by_work_package, load_registry

WP_ID = "WP-0A-02"


def _wp0a02_manifest() -> dict[str, object]:
    """Build WP-0A-02's manifest from the seeded registry."""
    document = load_registry(REGISTRY_PATH)
    packages = {package.wp_id: package for package in group_by_work_package(document)}
    return build_manifest(packages[WP_ID])


def test_manifest_declares_the_issued_env_hash() -> None:
    """WP-0A-02's manifest cites the currently issued env hash."""
    issued = read_issued()
    assert issued is not None, "WP-ENV-04 must have published an env hash"
    assert _wp0a02_manifest()["env_hash"] == issued


def test_manifest_clears_the_env_barrier() -> None:
    """The manifest is not refused start against the issued hash."""
    issued = read_issued()
    assert issued is not None
    verdict = check_manifest(_wp0a02_manifest(), issued)
    assert not verdict.blocked, verdict.as_line()


def test_manifest_without_env_hash_is_blocked() -> None:
    """A manifest declaring no env hash is refused start (barrier control)."""
    issued = read_issued() or "sha256:" + "a" * 64
    verdict = check_manifest({"wp_id": WP_ID}, issued)
    assert verdict.blocked
    assert verdict.reason == REASON_ABSENT
