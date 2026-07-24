"""The compatibility verdict and its source-attributed blocking reasons.

`10` FR-TRN-004 fixes the shape of every reason this engine emits: a block is not
trustworthy unless it names its source. A verdict that says "SmolVLA is blocked"
without stating that the ceiling is `max_state_dim=32`, that the dataset presents
48, and that the number was read from `configuration_smolvla.py` is exactly the
`[미확인]` (unattributed) claim FR-TRN-004 forbids. So `BlockingReason` carries the
four contract fields — `rule_id`, `observed`, `limit`, `source` — and the rendered
sentence that names them together.

These are pure carriers with no domain logic: the engine (`matrix`) fills them and
the frontend 창구 (S-10) renders them. Keeping them import-free is deliberate — a
verdict must be serialisable and comparable without pulling the introspection stack
in behind it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlockingReason:
    """One reason a policy is structurally incompatible, with its provenance.

    The four fields `10` FR-TRN-004 requires are `rule_id`, `observed`, `limit` and
    `source`; `field_name` and `message` are the rendered form the 창구 displays.

    Attributes:
        rule_id: The FR-TRN-017 sub-rule this block enforces, e.g. `FR-TRN-017f`
            for the dimension ceiling (which is FR-TRN-064) or `FR-TRN-017a` for
            ACT's single-observation-step rule.
        field_name: The config/dataset field the block is about, e.g.
            `max_state_dim`, `n_obs_steps`, `n_cameras`.
        observed: The value the dataset or training request presents.
        limit: The ceiling the installed policy config declares (or the fixed
            architectural bound the rule enforces, e.g. `1` for `n_obs_steps`).
        source: Absolute path of the LeRobot config file the limit was read from —
            the provenance FR-TRN-004 demands; empty only for rules whose bound is
            architectural rather than a config field.
        message: The operator-facing sentence naming field, observed and limit.
    """

    rule_id: str
    field_name: str
    observed: int | str
    limit: int | str
    source: str
    message: str


@dataclass(frozen=True)
class CompatibilityVerdict:
    """The verdict for one {policy, observation-config, projection} triple.

    `allowed` is false iff any blocking reason applies. The engine's job is to
    BLOCK: a verdict that lets a 48-dim dataset reach a 32-dim policy would let
    training start and `max_state_dim` truncate silently somewhere inside LeRobot
    (`10` FR-TRN-064 negative branch), so every reason here is a hard stop, never
    a warning.

    Attributes:
        policy_id: The policy family the verdict is for.
        allowed: True only when `blocking_reasons` is empty.
        blocking_reasons: Every reason that applies, one per violated rule; empty
            when the triple is buildable.
    """

    policy_id: str
    allowed: bool
    blocking_reasons: tuple[BlockingReason, ...]
