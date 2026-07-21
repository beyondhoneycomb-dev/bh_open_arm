"""Provenance manifest for the policy compatibility matrix.

The matrix's dimension ceilings are read from the installed policy configs, so the
matrix is only as trustworthy as the environment it was introspected against. Like
every Wave 0-C artifact (`06` §2.2), it therefore declares an `env_hash` and a
`normalization_hash`: the launch barriers (`registry.env.barrier`,
`registry.normalization.barrier`) refuse to start a workflow whose manifest carries
no hash or a superseded one, and the `env_hash` is exactly what would go stale if a
pin change moved a ceiling out from under the recorded matrix.

The hashes are read from what WP-ENV-04 and WP-N1-04 currently publish, never
invented. When a publication file is absent (bootstrap ordering) the slot is `None`,
which the barrier reads as "declares no hash" and refuses start — the same honesty
the dataset provenance uses, never a fabricated value that clears a barrier it
should not.
"""

from __future__ import annotations

from typing import Any

from registry.env.env_hash import read_issued as read_env_hash
from registry.normalization.content_hash import ISSUED_PATH as NORMALIZATION_ISSUED_PATH
from registry.normalization.content_hash import read_issued as read_normalization_hash

WP_ID = "WP-0C-08"


def build_provenance_manifest(matrix: dict[str, Any]) -> dict[str, Any]:
    """Build the provenance manifest for a computed matrix.

    Args:
        matrix: Facts about the computed matrix — the policies ranked, the
            observation configs and targets covered — to embed under `matrix`.

    Returns:
        (dict[str, Any]) A manifest carrying `wp_id`, the two currently-issued
            hashes, and the matrix facts. The barrier reads only `wp_id`,
            `env_hash` and `normalization_hash`; the rest is provenance.
    """
    return {
        "wp_id": WP_ID,
        "env_hash": read_env_hash(),
        "normalization_hash": read_normalization_hash(NORMALIZATION_ISSUED_PATH),
        "matrix": dict(matrix),
    }
