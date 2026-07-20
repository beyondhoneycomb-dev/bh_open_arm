"""Ownership glob expansion against the real file tree.

`06` §5 CI-02 expands `EXCLUSIVE` globs "to real files" rather than comparing glob
strings, because two different glob spellings can name the same file and a string
comparison would call that disjoint.
"""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=512)
def compile_glob(pattern: str) -> re.Pattern[str]:
    """Translate an ownership glob into an anchored regular expression.

    `**` crosses directory separators; `*` and `?` do not. A bare directory
    pattern is treated as covering nothing on its own — ownership is asserted over
    files, and `06` §3.3 writes the directory forms with an explicit `/**`.

    Args:
        pattern: Glob such as `backend/actuation/**` or `contracts/ws/x.json`.

    Returns:
        (re.Pattern[str]) Anchored matcher over root-relative POSIX paths.
    """
    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**", index):
            out.append(".*")
            index += 2
            continue
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        index += 1
    return re.compile(f"^{''.join(out)}$")


def split_globs(raw: str) -> tuple[str, ...]:
    """Split an ownership glob cell that may carry several comma-joined globs.

    The registry holds at least one `owns[].glob` value with two paths in a single
    string. Splitting keeps that from being read as one impossible path, which
    would silently expand to zero files and make the ownership invisible.

    Args:
        raw: Raw glob field value.

    Returns:
        (tuple[str, ...]) Individual glob patterns.
    """
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def expand(patterns: tuple[str, ...], files: tuple[str, ...]) -> frozenset[str]:
    """Expand globs against a file list.

    Args:
        patterns: Glob patterns.
        files: Root-relative POSIX paths.

    Returns:
        (frozenset[str]) Files matched by at least one pattern.
    """
    matchers = [compile_glob(pattern) for pattern in patterns]
    return frozenset(path for path in files if any(m.match(path) for m in matchers))


def matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    """Report whether a path matches any of the given globs.

    Args:
        path: Root-relative POSIX path.
        patterns: Glob patterns.

    Returns:
        (bool) True when at least one glob matches.
    """
    return any(compile_glob(pattern).match(path) for pattern in patterns)
