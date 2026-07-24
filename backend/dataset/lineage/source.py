"""Validation of a dataset source identity, reusing the recorder's `repo_id` rules.

A lineage record names the training dataset by its stamped `repo_id`. That name is
a recorder artefact (WP-3B-11): the recorder stamps a date-time suffix onto every
session's `repo_id` and refuses the `eval_` prefix reserved for policy evaluation.
Lineage tracks *training inputs*, so it consumes those same two rules rather than
forking them — `reject_eval_name` is imported from the recorder embed, and the
stamp format is the recorder's own constant. The only thing added here is the
inverse the recorder never needed: a check that an *incoming* `repo_id` was in fact
stamped, so a hand-typed or otherwise unprovenanced name cannot enter the store.
"""

from __future__ import annotations

from datetime import datetime

from backend.recorder.embed import reject_eval_name
from backend.recorder.embed.constants import (
    REPO_ID_STAMP_FORMAT,
    REPO_ID_STAMP_JOINER,
)

# The stamp is `<base><joiner><date>_<time>` where the date-time renders through the
# recorder's `%Y%m%d_%H%M%S`; that pattern itself contains one `_`, so a stamped id
# ends in two joiner-separated tokens (`YYYYMMDD`, `HHMMSS`). Parsing the tail back
# through the same format is the only faithful test that it was stamped.
_STAMP_TOKEN_COUNT = 2


class LineageSourceError(ValueError):
    """Raised when a dataset `repo_id` is not a valid recorder training source.

    The blocking cases: an `eval_` dataset name (a policy-evaluation artefact, never
    a training input) and a `repo_id` that was never stamped by the recorder, either
    of which would tie a checkpoint to a source with no honest provenance.
    """


def is_stamped_repo_id(repo_id: str) -> bool:
    """Report whether a `repo_id` carries the recorder's date-time stamp.

    Args:
        repo_id: The repository id to inspect.

    Returns:
        (bool) True when the trailing `YYYYMMDD_HHMMSS` tail parses under the
            recorder's stamp format.
    """
    tokens = repo_id.split(REPO_ID_STAMP_JOINER)
    if len(tokens) < _STAMP_TOKEN_COUNT:
        return False
    tail = REPO_ID_STAMP_JOINER.join(tokens[-_STAMP_TOKEN_COUNT:])
    try:
        datetime.strptime(tail, REPO_ID_STAMP_FORMAT)
    except ValueError:
        return False
    return True


def validate_dataset_repo_id(repo_id: str) -> None:
    """Refuse a `repo_id` that cannot be an honest training-dataset source.

    Reuses the recorder's `eval_`-name refusal and requires the recorder's stamp,
    so lineage only ever points at a dataset a recording session actually produced.

    Args:
        repo_id: The dataset's stamped repository id.

    Raises:
        LineageSourceError: On an `eval_` name or an unstamped `repo_id`.
    """
    try:
        reject_eval_name(repo_id)
    except Exception as rejected:  # RecorderNameError; re-raised as a lineage error
        raise LineageSourceError(str(rejected)) from rejected
    if not is_stamped_repo_id(repo_id):
        raise LineageSourceError(
            f"repo_id {repo_id!r} carries no recorder date-time stamp; a lineage source must be "
            "a dataset a recording session produced (WP-3B-11 stamp convention)"
        )
