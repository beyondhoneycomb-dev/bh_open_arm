"""Acceptance ②: no code path sets the CAN link — the unit does, the backend only verifies.

FR-SYS-006 forbids the backend from configuring the link. This reuses WP-0B-02's
`find_link_set_calls` — an AST scan for process spawns whose arguments form an `ip link set`
mutation — and extends it to WP-OPS-02's own product tree: neither backend code nor this
package spawns a link mutation. The setting instead lives in the rendered unit as data
systemd runs, which the positive assertion confirms so the check cannot pass vacuously.
"""

from __future__ import annotations

from pathlib import Path

from backend.can.link.staticcheck import find_link_set_calls
from ops.systemd.can_link import render_can_link_unit, unit_sets_the_link

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_spawns_no_link_mutation() -> None:
    """No backend process spawn configures a CAN link (the FR-SYS-006 invariant)."""
    assert find_link_set_calls(_REPO_ROOT / "backend") == []


def test_ops_systemd_spawns_no_link_mutation() -> None:
    """This package renders the bring-up as unit text; it never spawns it in Python."""
    assert find_link_set_calls(_REPO_ROOT / "ops" / "systemd") == []


def test_the_link_mutation_lives_in_the_unit() -> None:
    """The responsibility is fulfilled — the unit body carries the bring-up the code omits."""
    assert unit_sets_the_link(render_can_link_unit())
