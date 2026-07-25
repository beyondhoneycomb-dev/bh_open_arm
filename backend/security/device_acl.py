"""Device ACL / systemd sandbox for CAN TX — static runs here, live TX defers (`FR-OPS-029`).

`FR-OPS-029` is explicit that `flock` is only an agreement among well-behaved
processes: it cannot stop `cansend` or a second LeRobot instance from transmitting.
The mandatory, kernel-enforced complement is a **device ACL + systemd sandbox**
(`DeviceAllow` / `RestrictAddressFamilies`), and it must be present *together with*
the intruder detection (`FR-OPS-088`), because detection is not prevention.

That sandbox is already built and owned by `WP-OPS-01` (`ops.acl`): the shipped writer
unit and deny drop-in, the static checks over their text, the seccomp block harness,
and the vcan re-verification hook. This module composes them into the WP-5-08
acceptance surface. It splits `CG-5-08h` honestly:

- **Runs here** — the static soundness of the shipped ACL/sandbox config (directives
  present and correct, the deny drop-in actually denies `AF_CAN`, the sandbox does not
  silently disable `flock`). No CAN interface is needed for this.
- **Deferred** — the live `cansend`-TX-fail check (an unauthorised process cannot
  transmit; the authorised writer can, with zero over-block). That needs a CAN
  interface this dev host does not have (no vcan, no adapter). It is left to a
  re-verification hook and is **never** asserted green in the meantime (the ONE RULE):
  a faked bus-stop green is a safety lie.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ops import acl
from ops.acl.policy import DENY_DROPIN_FILENAME, WRITER_UNIT_FILENAME
from ops.acl.reverify import AclReverifyReport, reverify_on_interface, vcan_interface_from_env
from ops.acl.staticcheck import (
    find_dropin_not_denying_can,
    find_lock_dir_not_writable,
    find_missing_sandbox_directives,
)

# The directory the shipped writer unit and deny drop-in live in, resolved from the
# reused ACL package so a move of the units can never leave this path stale.
_UNITS_DIR = Path(acl.__file__).resolve().parent / "units"


@dataclass(frozen=True)
class DeviceAclStaticReport:
    """The static soundness verdict on the shipped ACL/sandbox config (runs here).

    Attributes:
        writer_unit: Absolute path of the authorised writer unit that was checked.
        deny_dropin: Absolute path of the deny drop-in that was checked.
        violations: One line per static defect; empty when the config is sound.
    """

    writer_unit: Path
    deny_dropin: Path
    violations: tuple[str, ...]

    @property
    def sound(self) -> bool:
        """Whether the shipped config passed every static check.

        Returns:
            (bool) True when there are no violations.
        """
        return not self.violations


@dataclass(frozen=True)
class LiveCanTxStatus:
    """The state of the live `cansend`-TX-fail check — deferred without a CAN interface.

    Attributes:
        deferred: True when no CAN interface is available, so the live check has not
            run and must not be asserted green.
        reason: Why it is deferred (or, when not deferred, the interface it can run on).
        interface: The vcan/CAN interface the hook would run against, or None.
    """

    deferred: bool
    reason: str
    interface: str | None


def static_config_report() -> DeviceAclStaticReport:
    """Run the ACL/sandbox static checks over the shipped unit files (`CG-5-08h` static).

    Reuses the `ops.acl` static checks rather than re-scanning: the writer unit must
    carry every sandbox directive with sound values, the deny drop-in must actually
    deny `AF_CAN`, and the sandbox must not seal the filesystem without re-granting the
    flock directory.

    Returns:
        (DeviceAclStaticReport) The soundness verdict, with one line per defect.
    """
    writer_unit = _UNITS_DIR / WRITER_UNIT_FILENAME
    deny_dropin = _UNITS_DIR / DENY_DROPIN_FILENAME
    writer_text = writer_unit.read_text(encoding="utf-8")
    dropin_text = deny_dropin.read_text(encoding="utf-8")

    violations: list[str] = []
    violations.extend(str(v) for v in find_missing_sandbox_directives(writer_text))
    violations.extend(str(v) for v in find_lock_dir_not_writable(writer_text))
    violations.extend(str(v) for v in find_dropin_not_denying_can(dropin_text))
    return DeviceAclStaticReport(
        writer_unit=writer_unit, deny_dropin=deny_dropin, violations=tuple(violations)
    )


def live_can_tx_status() -> LiveCanTxStatus:
    """Report whether the live `cansend`-TX-fail check can run, and why not.

    The live half (unauthorised process cannot transmit; authorised writer can) needs
    a CAN interface. When one is named through the ACL re-verify environment variable
    it can run; otherwise the check is deferred with a reason and must not be faked.

    Returns:
        (LiveCanTxStatus) Deferred with a reason when no interface is present.
    """
    interface = vcan_interface_from_env()
    if interface is None:
        return LiveCanTxStatus(
            deferred=True,
            reason=(
                "no vcan/CAN interface on this host; the live cansend-TX-fail check is deferred "
                "and must never be asserted green (ONE RULE). Set the ACL vcan env var on a rig "
                "to re-verify via reverify_live_can_tx()."
            ),
            interface=None,
        )
    return LiveCanTxStatus(
        deferred=False,
        reason=f"vcan/CAN interface {interface!r} available; the live check can run",
        interface=interface,
    )


def reverify_live_can_tx() -> AclReverifyReport:
    """Re-verification hook: run the live block acceptance against a real CAN interface.

    This is the deferred half of `CG-5-08h`, run only when a CAN interface exists. It
    fires the unauthorised probe (must be blocked before it binds) and the authorised
    writer (must transmit, zero over-block) on the interface named by the ACL vcan env
    var, reusing the `ops.acl` reverify logic.

    Returns:
        (AclReverifyReport) The live verdict; `matched` is the deferred acceptance.

    Raises:
        RuntimeError: If no CAN interface is available — the hook refuses to fabricate
            a result rather than asserting a green nothing produced.
    """
    interface = vcan_interface_from_env()
    if interface is None:
        raise RuntimeError(
            "reverify_live_can_tx called with no vcan/CAN interface; the live check cannot be "
            "faked (ONE RULE). It stays deferred until a rig provides an interface."
        )
    return reverify_on_interface(interface)
