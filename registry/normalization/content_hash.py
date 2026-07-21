"""Wave -1 normalization hash: the content identity of the settled corpus.

The hash answers exactly one question: is this the normalization every downstream
work package was spawned against (`SPINE` §5, `02a` §1.5 WP-N1-04). Its inputs are
the two artifacts a Wave -1 ruling is recorded in — the contradiction ledger
(`docs/plan/normalization/ledger.yaml`, WP-N1-02) and the gate ID namespace
mapping (`docs/plan/normalization/gate_spec_map.yaml`, WP-N1-03).

Determinism is the contract (`02a` §1.5 WP-N1-04 ①): the same settled content
yields the same hash, and any changed settled value yields a different one. The
serialization is canonical — object keys sorted, array order preserved — so a
semantically identical edit (reordered mapping keys, reflowed YAML) does not move
the hash while a changed value does.

It reuses the sorted-key / compact-separator shape of
`registry/contracts/canonical.py`, but deliberately NOT that module's projection.
The contract hash drops annotation keywords because a schema's prose is
non-normative; here every field is data whose change must move the hash. Dropping
a ledger field that happened to be named `example` would make two different
rulings hash identically, which is the opposite of what this hash exists to
guarantee.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from registry.normalization.loader import load_ledger

HASH_ALGORITHM = "sha256"
HASH_PREFIX = "sha256:"

REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUED_PATH = REPO_ROOT / "docs" / "plan" / "normalization" / "normalization_hash"

# Namespace the two inputs inside one object so that moving a value from the
# ledger to the map (or vice versa) is a different corpus and hashes differently.
LEDGER_KEY = "ledger"
GATE_MAP_KEY = "gate_map"

_HASH_TOKEN_LEN = len(HASH_PREFIX) + 64


def canonical_form(ledger_document: dict[str, Any], gate_map_document: dict[str, Any]) -> str:
    """Render the normalization corpus as deterministic text.

    Args:
        ledger_document: Parsed contradiction ledger.
        gate_map_document: Parsed gate ID namespace mapping.

    Returns:
        (str) Compact JSON with object keys sorted and array order preserved.
    """
    combined = {LEDGER_KEY: ledger_document, GATE_MAP_KEY: gate_map_document}
    return json.dumps(combined, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def normalization_hash(ledger_document: dict[str, Any], gate_map_document: dict[str, Any]) -> str:
    """Compute the content hash downstream manifests must cite.

    Args:
        ledger_document: Parsed contradiction ledger.
        gate_map_document: Parsed gate ID namespace mapping.

    Returns:
        (str) Hash as `sha256:<hex>`. The algorithm is carried in the value so a
            future change of algorithm is visible in the issued file instead of
            silently comparing unequal digests.
    """
    payload = canonical_form(ledger_document, gate_map_document).encode("utf-8")
    return f"{HASH_PREFIX}{hashlib.sha256(payload).hexdigest()}"


def _load_mapping(path: Path) -> dict[str, Any]:
    """Parse a YAML document, requiring a mapping at the root.

    This does not go through `registry.normalization.gate_map`: that module pulls
    in the corpus resolver, which imports the registry builder, and the builder is
    what calls this hash at seed time. Loading the map here with the same
    `yaml.safe_load` keeps the seed path free of that import cycle.

    Args:
        path: Path to a YAML file.

    Returns:
        (dict[str, Any]) The parsed mapping.

    Raises:
        TypeError: When the document does not parse to a mapping.
    """
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} did not parse to a mapping")
    return loaded


def issue(ledger_path: Path, gate_map_path: Path) -> str:
    """Compute the normalization hash from the two artifact files.

    A missing gate map is treated as an empty mapping rather than an error: the
    seeder runs at build time, and the ledger can exist before WP-N1-03 lands the
    map. The hash still depends deterministically on whatever content is present.

    Args:
        ledger_path: Path to the ledger YAML.
        gate_map_path: Path to the gate mapping YAML.

    Returns:
        (str) The issued `sha256:<hex>` hash.
    """
    ledger_document = load_ledger(ledger_path)
    gate_map_document = _load_mapping(gate_map_path) if gate_map_path.is_file() else {}
    return normalization_hash(ledger_document, gate_map_document)


def render_issued_file(digest: str) -> str:
    """Render the publication file's full text for a hash.

    Args:
        digest: The `sha256:<hex>` hash to publish.

    Returns:
        (str) File contents: a header stating the file's contract, then the hash
            token on its own final line for machine reading.
    """
    # The `#` lines are the published artifact's own header, not code comments:
    # this file is Korean plan content, so its header stays Korean like the
    # ledger's, while the last line carries the machine-read hash token.
    return (
        "# Wave -1 정규화 해시 — 원장(ledger.yaml) + 게이트 매핑(gate_spec_map.yaml)의\n"
        "# canonical 직렬화 콘텐츠 해시. 발행자 = WP-N1-04.\n"
        "# 모든 하류 WP 매니페스트는 normalization_hash로 이 값을 선언한다 — 불일치 = 착수 거부.\n"
        "# 재발행: python -m registry.normalization.cli --issue\n"
        f"{digest}\n"
    )


def write_issued(path: Path, digest: str) -> None:
    """Publish the issued hash to its file.

    Args:
        path: Destination of the publication file.
        digest: The `sha256:<hex>` hash to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_issued_file(digest), encoding="utf-8")


def read_issued(path: Path) -> str | None:
    """Read the published hash token, ignoring the header comment lines.

    Args:
        path: Path to the publication file.

    Returns:
        (str | None) The `sha256:<hex>` token, or None when the file is absent or
            holds no hash token.
    """
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.strip()
        if token.startswith(HASH_PREFIX) and len(token) == _HASH_TOKEN_LEN:
            return token
    return None
