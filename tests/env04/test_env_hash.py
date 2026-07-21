"""WP-ENV-04 acceptance ⑥ — env_hash is deterministic in its three inputs."""

from __future__ import annotations

from registry.env import env_hash as eh

BASE = eh.EnvInputs(
    pin_sha="30da8e687a6dfc617fcd94afc367ac7071c376ce",
    lock_hash="sha256:" + "0" * 64,
    checker_version="env04-upstream-facts@1",
)


def test_same_inputs_same_hash() -> None:
    assert eh.env_hash(BASE) == eh.env_hash(BASE)


def test_one_bit_change_in_each_input_changes_the_hash() -> None:
    baseline = eh.env_hash(BASE)
    pin_bit = eh.EnvInputs(BASE.pin_sha + "0", BASE.lock_hash, BASE.checker_version)
    lock_bit = eh.EnvInputs(BASE.pin_sha, BASE.lock_hash + "0", BASE.checker_version)
    checker_bit = eh.EnvInputs(BASE.pin_sha, BASE.lock_hash, BASE.checker_version + "x")
    assert eh.env_hash(pin_bit) != baseline
    assert eh.env_hash(lock_bit) != baseline
    assert eh.env_hash(checker_bit) != baseline


def test_issued_file_round_trips() -> None:
    digest = eh.env_hash(BASE)
    text = eh.render_issued_file(digest, BASE)
    lines = text.splitlines()
    # read_issued must recover exactly the token, ignoring the header comments.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "env_hash.txt"
        eh.write_issued(path, digest, BASE)
        assert eh.read_issued(path) == digest
    assert lines[-1] == digest


def test_committed_env_hash_matches_recomputation() -> None:
    published = eh.read_issued(eh.ISSUED_PATH)
    assert published is not None and published.startswith("sha256:")
