"""`Condition ∈ {NOMINAL, PERTURBED}` — the condition-definition schema (`02c` §3.5).

This WP owns the `Condition` definition; `02c` §3.5 인터페이스 계약 fixes exactly two
members and no more:

- `NOMINAL` — seeds drawn from the initial-state distribution the training data was
  collected under.
- `PERTURBED` — seeds drawn from a distribution with a predefined perturbation axis
  applied, where the axis is derived from the Wave 3C initial-state distribution.

The member values are plain strings on purpose. Downstream consumers (WP-4C-06's
checkpoint scorecard) take the condition as a generic string via a data-join and do
NOT import this enum, so the enum's owner is here and only here (`02c` DO-NOT-DUPLICATE:
"WP-4C-06 consumes the CONDITION as a generic value (string), NOT WP-4C-05's enum").
Serialising to the member's own name keeps that join stable without forking the type.
"""

from __future__ import annotations

from enum import Enum


class Condition(Enum):
    """The evaluation condition a rollout set was run under (`02c` §3.5).

    Two members, no third: a rollout is either drawn from the training-collection
    initial-state distribution (`NOMINAL`) or from a perturbed one (`PERTURBED`). The
    string value is the join key downstream reads by value, never by importing this type.
    """

    NOMINAL = "NOMINAL"
    PERTURBED = "PERTURBED"
