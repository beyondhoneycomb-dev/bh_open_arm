"""Deployment-target recognizer for the inference-path block matrix (WP-4B-04).

`02c` §2.4 fixes the enumeration: `DeploymentTarget ∈ {JETSON_NANO, JETSON_ORIN,
RTX_5090, RTX_A6000}` — SPINE §7's heterogeneous fleet, verbatim. A100/H100 are NOT in
it (`02c` §5.1 / §6.1): they carry no RT cores, so Isaac is unsupported and they are an
explicit exclusion, not an omission. The recognizer refuses them by name rather than
returning a fifth, unhandled target, because a silently-accepted datacenter GPU would
bypass every per-target gate this matrix exists to apply.

The four ids are also the fleet the environment layer owns (`targets.matrix`, WP-ENV-02).
`crosscheck_fleet_matrix` proves this enum still agrees with that fleet: a drift — the
ENV matrix gaining a target this enum lacks, or the exclusion set changing — is a
rejected build, not a silent divergence between two lists of the same targets.

`target_class` splits the fleet into the two conservative-default regimes `02c` §6.1
draws. A Jetson-class edge target with an unknown inference ceiling is blocked
conservatively (an unmeasured edge device is assumed too slow to run sync inference),
while an RTX-class workstation target with an unknown ceiling is left to its own
self-bench. That split is why the block matrix treats "no `11` §2.6 row" differently
per target.
"""

from __future__ import annotations

from enum import Enum, StrEnum


class DeploymentTarget(StrEnum):
    """The four deployment targets the block matrix renders a verdict for.

    Membership is the contract (`02c` §2.4): the matrix gates on exactly these, and a
    caller cannot introduce a fifth target — or slip an excluded datacenter GPU
    (A100/H100) past the per-target gates — without a code change this enum forces
    through review. The string value is the canonical fleet id (`targets.matrix`
    FLEET_TARGETS), so a target round-trips through `recognize_target`.
    """

    JETSON_NANO = "jetson_nano"
    JETSON_ORIN = "jetson_orin"
    RTX_5090 = "rtx_5090"
    RTX_A6000 = "rtx_a6000"


class TargetClass(Enum):
    """The two conservative-default regimes the fleet splits into (`02c` §6.1).

    JETSON — an edge target: when its inference ceiling is unknown (no `11` §2.6 row),
    sync is blocked conservatively, because an unmeasured edge device is assumed too
    slow to run synchronous inference at the configured fps. RTX — a workstation target:
    an unknown ceiling is left to its own self-bench, not blocked up front.
    """

    JETSON = "jetson"
    RTX = "rtx"


# The datacenter GPUs SPINE §7 excludes by name: no RT cores -> Isaac unsupported
# (`02c` §6.1). Named here so `recognize_target` can refuse them with the exclusion
# reason rather than a generic "unknown target".
EXCLUDED_TARGET_IDS: frozenset[str] = frozenset({"a100", "h100"})

_TARGET_CLASS: dict[DeploymentTarget, TargetClass] = {
    DeploymentTarget.JETSON_NANO: TargetClass.JETSON,
    DeploymentTarget.JETSON_ORIN: TargetClass.JETSON,
    DeploymentTarget.RTX_5090: TargetClass.RTX,
    DeploymentTarget.RTX_A6000: TargetClass.RTX,
}


class UnsupportedTargetError(ValueError):
    """Raised when a target id is not one of the four enumerated deployment targets.

    Carries whether the id was an explicit SPINE §7 exclusion (A100/H100) so a caller
    can distinguish "excluded by decision" from "unknown" — both are refused, but for
    different reasons the operator should see.

    Attributes:
        name: The offending target id, as supplied.
        excluded: True when the id is an A100/H100 SPINE §7 exclusion.
    """

    def __init__(self, name: str, excluded: bool) -> None:
        """Bind the offending id and whether it was an explicit exclusion.

        Args:
            name: The target id that failed recognition.
            excluded: True when the id is an A100/H100 exclusion, not merely unknown.
        """
        self.name = name
        self.excluded = excluded
        if excluded:
            message = (
                f"{name!r} is an explicit SPINE §7 exclusion (no RT cores -> Isaac "
                "unsupported, 02c §6.1); it is not a deployment target"
            )
        else:
            enumerated = tuple(target.value for target in DeploymentTarget)
            message = f"{name!r} is not one of the deployment targets {enumerated}"
        super().__init__(message)


def recognize_target(name: str) -> DeploymentTarget:
    """Resolve a target id string to a `DeploymentTarget`, refusing non-members.

    Args:
        name: A target id, e.g. `jetson_orin`. Matched case-insensitively against the
            canonical fleet ids.

    Returns:
        (DeploymentTarget) The enumerated target.

    Raises:
        UnsupportedTargetError: When `name` is an A100/H100 exclusion, or is unknown.
    """
    key = name.strip().lower()
    for target in DeploymentTarget:
        if target.value == key:
            return target
    raise UnsupportedTargetError(name, excluded=key in EXCLUDED_TARGET_IDS)


def target_class(target: DeploymentTarget) -> TargetClass:
    """Return the conservative-default regime a target belongs to (`02c` §6.1)."""
    return _TARGET_CLASS[target]


def crosscheck_fleet_matrix() -> tuple[str, ...]:
    """Prove this enum still agrees with the environment fleet matrix (WP-ENV-02).

    The four ids are owned as data by `targets.matrix` (SPINE §7); this enum restates
    them as a typed contract. A drift between the two — the ENV matrix gaining or
    dropping a fleet target, or the A100/H100 exclusion set changing — must fail a
    build, not diverge silently, because the matrix engine gates on this enum while the
    environment lock gates on that YAML.

    Returns:
        (tuple[str, ...]) One problem line per disagreement; empty when they agree.
    """
    from targets.matrix import EXCLUDED_TARGETS, FLEET_TARGETS

    problems: list[str] = []
    enum_ids = {target.value for target in DeploymentTarget}
    fleet_ids = set(FLEET_TARGETS)
    if enum_ids != fleet_ids:
        problems.append(
            f"DeploymentTarget {sorted(enum_ids)} != targets.matrix FLEET_TARGETS "
            f"{sorted(fleet_ids)}"
        )
    if set(EXCLUDED_TARGETS) != EXCLUDED_TARGET_IDS:
        problems.append(
            f"EXCLUDED_TARGET_IDS {sorted(EXCLUDED_TARGET_IDS)} != targets.matrix "
            f"EXCLUDED_TARGETS {sorted(EXCLUDED_TARGETS)}"
        )
    return tuple(problems)
