"""The anti-overconfidence disclaimer required by `12` NFR-SAF-009.

NFR-SAF-009 is a hard safety fact: on process death (SIGKILL / OOM / deadlock) or CAN
bus-off, a soft hold is impossible — the arm drops. A software watchdog can *delay* a drop;
it cannot *prevent* one. The fail-safe is mechanical: physical support, drop-zone isolation,
and an independent power-cutoff circuit. Software is never in that list.

This module holds that sentence as one canonical constant and provides the static check that
proves it is actually embedded — both in the crash-report contract document and in the text
a crash report renders. A watchdog that quietly implied it could save the arm would be worse
than none, so the claim it must *not* make is checked as rigorously as any behaviour.
"""

from __future__ import annotations

from pathlib import Path

# The load-bearing clause the static check searches for. Kept short and exact so a
# paraphrase that drifts from the safety fact cannot pass as if it were the fact.
REQUIRED_DISCLAIMER_PHRASE = "cannot prevent a drop"

# The full canonical disclaimer, embedded verbatim in the crash report and the contract doc.
DROP_DISCLAIMER = (
    "The software watchdog cannot prevent a drop; it can only delay one. "
    "NFR-SAF-009: on process death (SIGKILL / OOM / deadlock) or CAN bus-off a soft hold "
    "is impossible, so the arm drops. The fail-safe is mechanical support, drop-zone "
    "isolation, and an independent power-cutoff circuit — never software."
)

# The contract document that ships alongside this package, whose presence of the phrase the
# acceptance gate ⑨ checks statically.
CRASH_REPORT_CONTRACT_DOC = Path(__file__).resolve().parent / "crash_report_contract.md"


class MissingDropDisclaimerError(RuntimeError):
    """Text that was required to carry the NFR-SAF-009 disclaimer did not."""


def contains_disclaimer(text: str) -> bool:
    """Report whether `text` carries the required disclaimer phrase.

    Args:
        text: Any candidate text (a rendered report, a document body).

    Returns:
        (bool) True when the load-bearing phrase is present.
    """
    return REQUIRED_DISCLAIMER_PHRASE in text


def assert_disclaimer_present(text: str) -> None:
    """Raise unless `text` carries the required disclaimer phrase.

    Args:
        text: Candidate text.

    Raises:
        MissingDropDisclaimerError: If the phrase is absent.
    """
    if not contains_disclaimer(text):
        raise MissingDropDisclaimerError(
            f"required NFR-SAF-009 disclaimer phrase {REQUIRED_DISCLAIMER_PHRASE!r} is absent"
        )


def doc_has_disclaimer(doc_path: Path = CRASH_REPORT_CONTRACT_DOC) -> bool:
    """Report whether the crash-report contract document carries the disclaimer.

    Args:
        doc_path: Path to the contract document.

    Returns:
        (bool) True when the document exists and contains the phrase.
    """
    return doc_path.is_file() and contains_disclaimer(doc_path.read_text(encoding="utf-8"))
