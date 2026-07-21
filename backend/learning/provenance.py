"""Provenance manifest for a generated synthetic dataset.

Wave 0-C is downstream of WP-ENV-04 (the environment hash) and WP-N1-04 (the
normalization hash). `06` §2.2 gives every work-package manifest an `env_hash` and
a `normalization_hash` slot, and the launch barriers refuse to start a workflow
whose manifest declares no hash or a superseded one (`registry.env.barrier`,
`registry.normalization.barrier`). A synthetic dataset is a build artifact of this
band, so it carries the same two hashes: they record the environment and the
normalization ruleset the dataset was generated against, and they let the barriers
decide whether a consumer built against a newer environment may still trust it.

The hashes are read from the values WP-ENV-04 and WP-N1-04 currently publish, not
invented here. When a publication file is absent (bootstrap ordering) the slot is
`None`, which the barrier reads as "declares no hash" and refuses start — the same
honesty the seeder uses, never a fabricated value that would clear a barrier it
should not.
"""

from __future__ import annotations

from typing import Any

from registry.env.env_hash import read_issued as read_env_hash
from registry.normalization.content_hash import ISSUED_PATH as NORMALIZATION_ISSUED_PATH
from registry.normalization.content_hash import read_issued as read_normalization_hash

WP_ID = "WP-0C-07"


def build_provenance_manifest(dataset: dict[str, Any]) -> dict[str, Any]:
    """Build the provenance manifest for a generated dataset.

    Args:
        dataset: Facts about the generated dataset — repo id, root, dimensions,
            frame and episode counts — to embed under the `dataset` key.

    Returns:
        (dict[str, Any]) A manifest carrying `wp_id`, the two currently-issued
        hashes, and the dataset facts. The barrier reads only `wp_id`, `env_hash`
        and `normalization_hash`; the rest is provenance for a human reader.
    """
    return {
        "wp_id": WP_ID,
        "env_hash": read_env_hash(),
        "normalization_hash": read_normalization_hash(NORMALIZATION_ISSUED_PATH),
        "dataset": dict(dataset),
    }
