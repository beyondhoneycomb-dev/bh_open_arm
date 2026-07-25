"""Tag -> registry error code, or an explicit "no code" (CG-4C-04d).

`02c` §3.4 requires every tag to map to a `14` §2.10 error code or to say, explicitly,
that no code applies. "Explicit" is the point: a tag that silently has no code is
indistinguishable from one whose code was forgotten. So every tag maps to a value, and
the no-code case is the named sentinel `NO_CODE` — deliberately not a valid `OA-*`
string — rather than a bare `None` that could be an oversight.

The codes are **reused, never re-declared**. Where WP-4A-08 already fixed the code for
an event, this module reads that same constant so the two cannot drift:

- `POLICY_RUNAWAY` -> `RUNAWAY_ERROR_CODE` (the committed `OA-INF-003`).
- `REMOTE_DISCONNECT` / `REMOTE_EMPTY_ACTION` -> `error_code_for(...)` of the committed
  `DisconnectClass`, which is exactly the transport-vs-empty split (`OA-INF-001` vs
  `OA-INF-002`) CG-4A-08d already enforces.
- `POLICY_OUT_OF_BOUNDS` -> `OA-CTL-002` (joint-limit clamp), the same code
  `contracts.errors.integration.code_for_clamp` maps `ClampReason.JOINT_LIMIT` to;
  named here by registry symbol, not copied as a literal.
- `QUEUE_STARVATION` -> `OA-INF-002` (action queue exhausted), the queue-exhaustion code.

The remaining tags have **no** registry code and say so with `NO_CODE`. Four machine
tags (`POLICY_INVALID_OUTPUT`, `SAFETY_STOP`, `COLLISION`, `TORQUE_LIMIT`) name events
the frozen registry has no code for — a NaN-reject counter, a safety-stop-as-event
(the stop is a Wave 2C reaction category, not itself a fault code; the triggering
condition carries the code), a sim collision, and a sim `actuatorfrcrange` hit whose
only near-neighbour, `OA-MOT-00E`, is a Damiao hardware overload nibble in a different
subsystem. This band invents no code (the registry is frozen), so the honest mapping is
`NO_CODE`. The four deferred tags are policy/environment/labeler judgments, not system
faults, and carry `NO_CODE` too.
"""

from __future__ import annotations

from typing import Final

from backend.eval.taxonomy.tags import FailureTag
from backend.inference.runaway import (
    RUNAWAY_ERROR_CODE,
    DisconnectClass,
    error_code_for,
)
from contracts.errors import codes

# The explicit "no registry code applies" marker required by CG-4C-04d. It is not a
# valid OA-<domain>-<3> string on purpose, so it can never be mistaken for a real code
# nor pass the registry's code grammar.
NO_CODE: Final[str] = "NO_CODE"

# Each tag to its canonical registry code or NO_CODE. Codes are read from the committed
# WP-4A-08 constants where those exist, so this mapping tracks the source of truth
# rather than restating it.
TAG_ERROR_CODES: dict[FailureTag, str] = {
    # Auto-derived machine tags with a registry code.
    FailureTag.POLICY_OUT_OF_BOUNDS: codes.OA_CTL_002,
    FailureTag.POLICY_RUNAWAY: RUNAWAY_ERROR_CODE,
    FailureTag.QUEUE_STARVATION: codes.OA_INF_002,
    FailureTag.REMOTE_DISCONNECT: error_code_for(DisconnectClass.TRANSPORT),
    FailureTag.REMOTE_EMPTY_ACTION: error_code_for(DisconnectClass.EMPTY_ACTION),
    # Auto-derived machine tags the frozen registry has no code for (band invents none).
    FailureTag.POLICY_INVALID_OUTPUT: NO_CODE,
    FailureTag.SAFETY_STOP: NO_CODE,
    FailureTag.COLLISION: NO_CODE,
    FailureTag.TORQUE_LIMIT: NO_CODE,
    # Deferred tags — human/FSM judgments, not system faults.
    FailureTag.POLICY_WRONG_ACTION: NO_CODE,
    FailureTag.RESET_ERROR: NO_CODE,
    FailureTag.TIMEOUT: NO_CODE,
    FailureTag.AMBIGUOUS: NO_CODE,
}


def code_for_tag(tag: FailureTag) -> str:
    """Return the registry code naming a tag, or `NO_CODE` when none applies.

    Args:
        tag: The failure tag to map.

    Returns:
        (str) A registered `OA-*` code string, or `NO_CODE` when the tag has no code.
    """
    return TAG_ERROR_CODES[tag]


def has_registry_code(tag: FailureTag) -> bool:
    """Whether a tag maps to a real registry code rather than `NO_CODE`.

    Args:
        tag: The failure tag to test.

    Returns:
        (bool) True when the tag carries a registered `OA-*` code.
    """
    return TAG_ERROR_CODES[tag] != NO_CODE
