"""WP-ENV-04 — the environment hash: content identity of the pinned toolchain.

`env_hash = sha256({pin_sha, lock_hash, checker_version})` (`02a` §2.2 WP-ENV-04).
Every downstream WP manifest declares this value; a mismatch refuses start, and a
bump makes every un-integrated `SHAPE-IM` descendant stale via the same closure the
normalization hash uses (`registry.normalization.stale`, seeded on `env_hash:
CHANGED`).

Determinism is the contract (acceptance ⑥): the same three inputs yield the same
hash and any 1-bit change yields a different one. The three inputs are:
  * pin_sha         — the pinned LeRobot commit (`deps/lerobot.pin`).
  * lock_hash       — sha256 of the lockfile bytes (`uv.lock`, WP-ENV-02).
  * checker_version — the contract-regression checker's version
                      (`registry.env.upstream.CHECKER_VERSION`).

This module is stdlib-only: it takes the three inputs as strings/bytes and never
imports the robot stack, so the hash can be issued and verified in the light lane.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUED_PATH = REPO_ROOT / "registry" / "env" / "env_hash.txt"
LOCK_PATH = REPO_ROOT / "uv.lock"

HASH_PREFIX = "sha256:"
_HASH_TOKEN_LEN = len(HASH_PREFIX) + 64

PIN_SHA_KEY = "pin_sha"
LOCK_HASH_KEY = "lock_hash"
CHECKER_VERSION_KEY = "checker_version"


@dataclass(frozen=True)
class EnvInputs:
    """The three inputs the env hash is a function of.

    Attributes:
        pin_sha: The pinned LeRobot commit SHA.
        lock_hash: sha256 of the lockfile bytes, as `sha256:<hex>`.
        checker_version: The contract-regression checker version string.
    """

    pin_sha: str
    lock_hash: str
    checker_version: str


def canonical_form(inputs: EnvInputs) -> str:
    """Render the env inputs as deterministic text.

    Args:
        inputs: The three env inputs.

    Returns:
        (str) Compact JSON with object keys sorted.
    """
    payload = {
        PIN_SHA_KEY: inputs.pin_sha,
        LOCK_HASH_KEY: inputs.lock_hash,
        CHECKER_VERSION_KEY: inputs.checker_version,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def env_hash(inputs: EnvInputs) -> str:
    """Compute the environment hash downstream manifests must cite.

    Args:
        inputs: The three env inputs.

    Returns:
        (str) `sha256:<hex>`; the algorithm is carried in the value so a future
            change of algorithm is visible instead of silently comparing unequal.
    """
    digest = hashlib.sha256(canonical_form(inputs).encode("utf-8")).hexdigest()
    return f"{HASH_PREFIX}{digest}"


def lock_hash_of(lock_path: Path = LOCK_PATH) -> str:
    """Hash the lockfile bytes.

    A missing lockfile hashes to a stable sentinel rather than raising: the env
    hash still depends deterministically on the absence, and the lockfile-absent
    state is itself a distinct environment.

    Args:
        lock_path: Path to `uv.lock`.

    Returns:
        (str) `sha256:<hex>` of the file bytes, or of a fixed sentinel when absent.
    """
    data = lock_path.read_bytes() if lock_path.is_file() else b"<no-lockfile>"
    return f"{HASH_PREFIX}{hashlib.sha256(data).hexdigest()}"


def render_issued_file(digest: str, inputs: EnvInputs) -> str:
    """Render the publication file's full text for a hash.

    Args:
        digest: The `sha256:<hex>` env hash.
        inputs: The inputs it was computed from, recorded for provenance.

    Returns:
        (str) File contents: a header stating the contract and the three inputs,
            then the hash token on its own final line for machine reading.
    """
    return (
        "# WP-ENV-04 environment hash — sha256({pin_sha, lock_hash, checker_version}).\n"
        f"# pin_sha        = {inputs.pin_sha}\n"
        f"# lock_hash      = {inputs.lock_hash}\n"
        f"# checker_version = {inputs.checker_version}\n"
        "# Every downstream WP manifest declares this as env_hash — mismatch = start refused.\n"
        "# Reissue: python -m registry.env.cli --issue\n"
        f"{digest}\n"
    )


def write_issued(path: Path, digest: str, inputs: EnvInputs) -> None:
    """Publish the issued env hash to its file.

    Args:
        path: Destination of the publication file.
        digest: The env hash to write.
        inputs: The inputs it was computed from.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_issued_file(digest, inputs), encoding="utf-8")


def read_issued(path: Path = ISSUED_PATH) -> str | None:
    """Read the published env-hash token, ignoring header comment lines.

    Args:
        path: Path to the publication file.

    Returns:
        (str | None) The `sha256:<hex>` token, or None when absent.
    """
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.strip()
        if token.startswith(HASH_PREFIX) and len(token) == _HASH_TOKEN_LEN:
            return token
    return None
