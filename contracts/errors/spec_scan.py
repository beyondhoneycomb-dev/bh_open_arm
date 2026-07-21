"""Read OA-* codes straight from the spec, so coverage is a real cross-check.

Acceptance ① and ⑧ are grep cross-checks: the registry must cover what the spec
actually writes, not a list transcribed once and trusted forever. So these
helpers reconstruct the code set from the source documents — 14 §2.10 (the canon,
which writes a domain prefix plus bare numbers) and full `OA-...` tokens wherever
they appear — and the checkers compare the registry against that live reading.
"""

from __future__ import annotations

import re
from pathlib import Path

# 14 §2.10 writes a row as `OA-CAN-xxx | ... | `001` ... `007` ...`, so a code is
# the row's domain prefix crossed with each 3-char number token on that row.
_DOMAIN_PREFIX = re.compile(r"OA-([A-Z]+)-xxx")
_NUMBER_TOKEN = re.compile(r"`([0-9A-F]{3})`")
_FULL_CODE = re.compile(r"OA-[A-Z]+-[0-9A-F]{3}")

# The canonical registry self-declares with this phrase; a non-canon document
# carrying it is asserting a second registry (acceptance ⑩), unless it is merely
# pointing at the canon, which every legitimate reference does by naming doc 14.
_CANON_ASSERTION = "에러코드 정본 레지스트리"
_CANON_DOC_NUMBER = "14"


def section_text(document: Path, heading: str) -> str:
    """Return the body of a Markdown section, heading to the next same-level one.

    Args:
        document: The Markdown file to read.
        heading: The exact heading text to slice from, e.g. `### 2.10`.

    Returns:
        (str) The section body, or empty when the heading is absent.
    """
    text = document.read_text(encoding="utf-8")
    start = text.find(heading)
    if start == -1:
        return ""
    level = heading[: len(heading) - len(heading.lstrip("#"))]
    rest = text[start + len(heading) :]
    stop = rest.find(f"\n{level} ")
    return rest if stop == -1 else rest[:stop]


def canon_codes(spec14: Path) -> set[str]:
    """Reconstruct every OA-* code the 14 §2.10 table declares.

    Args:
        spec14: Path to `docs/spec/14-시스템-운영.md`.

    Returns:
        (set[str]) Full codes such as `OA-CAN-001`, `OA-MOT-00E`.
    """
    body = section_text(spec14, "### 2.10")
    found: set[str] = set()
    for line in body.splitlines():
        prefix = _DOMAIN_PREFIX.search(line)
        if prefix is None:
            continue
        domain = prefix.group(1)
        for number in _NUMBER_TOKEN.findall(line):
            found.add(f"OA-{domain}-{number}")
    return found


def full_code_tokens(document: Path) -> set[str]:
    """Return every full `OA-<domain>-<num>` token literally present in a document.

    Args:
        document: The Markdown file to scan.

    Returns:
        (set[str]) Full code tokens.
    """
    return set(_FULL_CODE.findall(document.read_text(encoding="utf-8")))


def asserts_second_registry(document: Path, canon: Path) -> bool:
    """Report whether a document declares itself an error-code registry.

    A legitimate reference names the canon (doc 14) on the same line; a second
    registry asserts canonicity for itself without doing so. The canon document
    is never a second registry of itself.

    Args:
        document: The Markdown file to test.
        canon: Path to the canonical spec (14), which is exempt.

    Returns:
        (bool) True when the document asserts a second, competing registry.
    """
    if document.resolve() == canon.resolve():
        return False
    for line in document.read_text(encoding="utf-8").splitlines():
        if _CANON_ASSERTION in line and _CANON_DOC_NUMBER not in line:
            return True
    return False
