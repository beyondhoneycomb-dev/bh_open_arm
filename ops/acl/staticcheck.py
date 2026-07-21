"""Static checks over installed unit text — the invariants a unit file alone cannot vouch for.

A `.service` file is just text until systemd loads it; nothing in the file stops an editor
from deleting `RestrictAddressFamilies`, widening it to `AF_INET`, or forgetting the one
`ReadWritePaths` line that keeps flock alive. These scans are what reject such a file before
it is installed, and they read the text because the text is what gets installed.

Three things are checked, mapping to the acceptance gates:

- **Sandbox directives present and sound** (④) — every `REQUIRED_DIRECTIVES` entry appears,
  the family allowlist actually admits `AF_CAN` and actually excludes the forbidden IP
  families, and the device ACL is `closed`.
- **flock kept alive** (③) — under `ProtectSystem=strict`/`full` the canonical lock directory
  must be re-granted via `ReadWritePaths`, or the mandatory layer has silently disabled the
  cooperative one.
- **Deny drop-in really denies** (①, static side) — the drop-in that blocks non-writer units
  must carry the `~AF_CAN` deny form; a drop-in that names the directive but forgets the `~`
  would *allow* CAN, the exact inversion the check exists to catch.
"""

from __future__ import annotations

from dataclasses import dataclass

from ops.acl.policy import (
    AUTHORIZED_FAMILIES,
    CAN_FAMILY,
    DEVICE_POLICY_CLOSED,
    FORBIDDEN_FAMILIES,
    LOCK_DIR_MUST_BE_WRITABLE,
    REQUIRED_DIRECTIVES,
)
from ops.acl.unitfile import UnitFile, parse_unit

_SERVICE = "Service"
_RESTRICT_FAMILIES = "RestrictAddressFamilies"
_DEVICE_POLICY = "DevicePolicy"
_PROTECT_SYSTEM = "ProtectSystem"
_READ_WRITE_PATHS = "ReadWritePaths"
_INVERT = "~"
_SEALED_PROTECT_SYSTEM = ("strict", "full")


@dataclass(frozen=True)
class DirectiveViolation:
    """A rejected unit, named by the directive that is wrong and why.

    Attributes:
        key: The directive at fault (or a synthetic name for a whole-unit condition).
        reason: What is wrong, phrased for the report.
    """

    key: str
    reason: str

    def __str__(self) -> str:
        return f"{self.key}: {self.reason}"


@dataclass(frozen=True)
class AddressFamilyRule:
    """The effective `RestrictAddressFamilies` policy of a unit.

    systemd reads a value beginning with `~` as an inversion, so a unit expresses either
    an allowlist (families it permits) or a denylist (families it forbids). Both sets are
    kept because the writer unit is checked against its allowlist and the deny drop-in
    against its denylist, and conflating them would let one masquerade as the other.

    Attributes:
        present: Whether the directive appears at all.
        allowed: Families named by non-inverted assignments.
        denied: Families named by inverted (`~`) assignments.
    """

    present: bool
    allowed: frozenset[str]
    denied: frozenset[str]


def address_family_rule(unit: UnitFile) -> AddressFamilyRule:
    """Interpret a unit's `RestrictAddressFamilies` assignments into allow/deny sets.

    Args:
        unit: Parsed unit.

    Returns:
        (AddressFamilyRule) The families the unit allows and the families it denies.
    """
    values = unit.values(_SERVICE, _RESTRICT_FAMILIES)
    allowed: set[str] = set()
    denied: set[str] = set()
    for value in values:
        inverted = value.startswith(_INVERT)
        body = value[1:] if inverted else value
        target = denied if inverted else allowed
        target.update(token for token in body.split() if token)
    return AddressFamilyRule(
        present=unit.has(_SERVICE, _RESTRICT_FAMILIES),
        allowed=frozenset(allowed),
        denied=frozenset(denied),
    )


def _check_address_families(unit: UnitFile) -> list[DirectiveViolation]:
    """Check the writer's family allowlist admits AF_CAN and excludes the IP families.

    Args:
        unit: Parsed writer unit.

    Returns:
        (list[DirectiveViolation]) Empty when the allowlist is sound.
    """
    rule = address_family_rule(unit)
    if not rule.present:
        return []  # Presence is reported by the REQUIRED_DIRECTIVES scan, not duplicated here.
    violations: list[DirectiveViolation] = []
    if rule.denied:
        violations.append(
            DirectiveViolation(
                _RESTRICT_FAMILIES,
                f"writer unit uses an inverted (deny) form {sorted(rule.denied)}; it must be "
                f"an allowlist admitting {CAN_FAMILY}",
            )
        )
    if CAN_FAMILY not in rule.allowed:
        violations.append(
            DirectiveViolation(
                _RESTRICT_FAMILIES,
                f"allowlist {sorted(rule.allowed)} does not admit {CAN_FAMILY}; the authorized "
                "writer could not open the bus",
            )
        )
    leaked = sorted(rule.allowed.intersection(FORBIDDEN_FAMILIES))
    if leaked:
        violations.append(
            DirectiveViolation(
                _RESTRICT_FAMILIES,
                f"allowlist admits {leaked}; a CAN writer must not reach the IP families",
            )
        )
    return violations


def find_missing_sandbox_directives(unit_text: str) -> list[DirectiveViolation]:
    """Report the sandbox directives a would-be writer unit is missing or has wrong (④).

    Args:
        unit_text: Body of the `.service` unit.

    Returns:
        (list[DirectiveViolation]) One per missing directive or unsound value, in policy order.
    """
    unit = parse_unit(unit_text)
    violations: list[DirectiveViolation] = []
    for directive in REQUIRED_DIRECTIVES:
        if not unit.has(directive.section, directive.key):
            violations.append(DirectiveViolation(directive.key, f"absent — {directive.rationale}"))

    device_policy = unit.scalar(_SERVICE, _DEVICE_POLICY)
    if device_policy is not None and device_policy != DEVICE_POLICY_CLOSED:
        violations.append(
            DirectiveViolation(
                _DEVICE_POLICY,
                f"is {device_policy!r}, not {DEVICE_POLICY_CLOSED!r}; the device ACL is not closed",
            )
        )

    violations.extend(_check_address_families(unit))
    return violations


def find_lock_dir_not_writable(unit_text: str) -> list[DirectiveViolation]:
    """Report a sealed-filesystem unit that has not re-granted the flock directory (③).

    Under `ProtectSystem=strict`/`full` the whole hierarchy is read-only, so the WP-0B-01
    lock file cannot be created unless its directory is listed in `ReadWritePaths`. A unit
    that seals the filesystem without that grant disables flock — the mandatory layer
    quietly replacing the cooperative one instead of complementing it.

    Args:
        unit_text: Body of the `.service` unit.

    Returns:
        (list[DirectiveViolation]) Empty unless the filesystem is sealed and the lock
        directory is not writable.
    """
    unit = parse_unit(unit_text)
    protect_system = unit.scalar(_SERVICE, _PROTECT_SYSTEM)
    if protect_system not in _SEALED_PROTECT_SYSTEM:
        return []
    writable = unit.values(_SERVICE, _READ_WRITE_PATHS)
    if any(_grants(path, LOCK_DIR_MUST_BE_WRITABLE) for path in writable):
        return []
    return [
        DirectiveViolation(
            _READ_WRITE_PATHS,
            f"ProtectSystem={protect_system} seals the filesystem but {LOCK_DIR_MUST_BE_WRITABLE} "
            "is not re-granted; the flock layer (WP-0B-01) would be disabled by the sandbox",
        )
    ]


def find_dropin_not_denying_can(dropin_text: str) -> list[DirectiveViolation]:
    """Report a non-writer deny drop-in that fails to actually deny AF_CAN (①, static).

    Args:
        dropin_text: Body of the deny drop-in `.conf`.

    Returns:
        (list[DirectiveViolation]) Empty only when the drop-in denies `AF_CAN`.
    """
    rule = address_family_rule(parse_unit(dropin_text))
    if CAN_FAMILY in rule.denied:
        return []
    if CAN_FAMILY in rule.allowed:
        return [
            DirectiveViolation(
                _RESTRICT_FAMILIES,
                f"drop-in ALLOWS {CAN_FAMILY} instead of denying it (missing the ~ inversion)",
            )
        ]
    return [
        DirectiveViolation(
            _RESTRICT_FAMILIES,
            f"drop-in does not deny {CAN_FAMILY}; non-writer processes could open the bus",
        )
    ]


def _grants(read_write_path: str, required_dir: str) -> bool:
    """Whether a `ReadWritePaths` entry re-grants at least the required directory.

    A grant of the directory itself or of a parent of it makes the lock file creatable.

    Args:
        read_write_path: One `ReadWritePaths` token.
        required_dir: The directory that must end up writable.

    Returns:
        (bool) True when the entry covers the required directory.
    """
    grant = read_write_path.lstrip("-+").rstrip("/")
    target = required_dir.rstrip("/")
    return target == grant or target.startswith(grant + "/")


# The two shipped families of families, re-exported so tests can state the intended
# allowlist without reaching back into policy for a constant the checks already read.
INTENDED_WRITER_ALLOWLIST = frozenset(AUTHORIZED_FAMILIES)
