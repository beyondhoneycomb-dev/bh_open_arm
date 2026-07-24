"""WP-3D-07 ①: a v3.0 import runs one-way (isolated), tagged and non-pushing.

`02b` §8.2 WP-3D-07 ②: the import is a one-way legacy OpenArm -> LeRobot v3.0 path run
in an isolated environment. This module checks the path runs end to end on our side:
the guard authorizes the import and composes the isolated invocation, the accepted
artifact is tagged `IMPORTED_LEGACY`, it validates VALID on the synthetic grid, and the
reused `WP-OPS-04` guard confirms nothing pushes to the Hub.
"""

from __future__ import annotations

from backend.dataset.import_export import (
    IMPORT_ONLY_FORMAT,
    ISOLATED_ENV_EXTRA,
    DatasetProvenance,
    Validity,
    accept_imported_dataset,
    no_hub_upload_decision,
    plan_import,
)
from tests.wp3d07 import support


def test_plan_import_composes_isolated_invocation() -> None:
    """`plan_import` authorizes the v3.0 import and targets the isolated environment."""
    invocation = plan_import("/data/legacy", "/data/out", fps=support.FIXTURE_FPS)
    assert invocation.env_extra == ISOLATED_ENV_EXTRA
    assert "--format" in invocation.argv
    assert invocation.argv[invocation.argv.index("--format") + 1] == IMPORT_ONLY_FORMAT
    # The bound is unresolved on purpose (`08` §2.9 / `NFR-REC-007`): None, not a guess.
    assert invocation.python_lower_bound is None


def test_import_is_one_way_only() -> None:
    """The composed argv converts legacy -> v3.0, never the other direction."""
    invocation = plan_import("/data/legacy", "/data/out", fps=support.FIXTURE_FPS)
    fmt_index = invocation.argv.index("--format")
    # The only format on the line is the import target; no export format appears.
    assert invocation.argv[fmt_index + 1] == IMPORT_ONLY_FORMAT
    assert "gr00t" not in invocation.argv
    assert "lerobot_v2.1" not in invocation.argv


def test_accepted_import_is_valid_and_tagged() -> None:
    """Accepting a well-formed import yields VALID with `IMPORTED_LEGACY` provenance."""
    outcome = accept_imported_dataset(support.imported_dataset(), support.native_facts())
    assert outcome.provenance is DatasetProvenance.IMPORTED_LEGACY
    assert outcome.validity is Validity.VALID
    assert outcome.load.validity is Validity.VALID


def test_import_never_pushes_to_hub() -> None:
    """The import path reuses the `WP-OPS-04` guard and resolves push_to_hub false."""
    outcome = accept_imported_dataset(support.imported_dataset(), support.native_facts())
    assert outcome.push_decision.push_to_hub is False
    # The same guard, called directly, agrees — one enforcement point, no local copy.
    assert no_hub_upload_decision().push_to_hub is False
