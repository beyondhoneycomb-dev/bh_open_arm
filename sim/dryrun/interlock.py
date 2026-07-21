"""The real-transmission hard-block interlock (`09` FR-SIM-033).

This is the safety core of WP-0C-09. A dry-run verdict with any violation must
**hard-block** real-robot transmission, and the *only* way past a failing verdict
is an explicit operator modal confirmation that acknowledges every violated check.
There is no implicit bypass — that absence is the requirement (acceptance ③, ④).

Two properties enforce it, one at runtime and one structurally:

- A ``TransmissionGrant`` is the sole token that authorises transmission, and it
  cannot be constructed outside this module: its ``__init__`` demands a private
  key object only this module holds. No other file can fabricate authorisation.
- Exactly two functions mint a grant. ``authorize_transmission`` mints one only
  for a *passing* verdict and raises ``HardBlockError`` otherwise — it has no
  bypass. ``authorize_with_modal_confirm`` is the one sanctioned bypass and mints
  a grant for a failing verdict *only* against a valid ``ModalConfirmation`` that
  acknowledges every violated item. A confirmation that does not cover a violation
  is refused, so an operator cannot blanket-wave a failure through.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sim.dryrun.violation import DryRunCheck, DryRunVerdict

# The private key gating TransmissionGrant construction. Holding it is what proves a
# grant came from this module's two sanctioned mints and not from fabricated code.
_GRANT_KEY = object()


class HardBlockError(RuntimeError):
    """Raised when transmission is attempted on a failing verdict without a confirm.

    `09` FR-SIM-033: a failed dry-run hard-blocks real transmission.
    """


@dataclass(frozen=True)
class ModalConfirmation:
    """An explicit operator override acknowledging specific dry-run violations.

    A confirmation is valid only when an operator is named, it is confirmed, and it
    acknowledges *every* check the verdict violated. Acknowledging a subset is not
    enough — the interlock refuses it — so there is no way to bypass a violation the
    operator did not explicitly see.

    Attributes:
        operator: The acknowledging operator's identifier; must be non-empty.
        confirmed: Whether the operator actually confirmed the override.
        acknowledged_items: The dry-run checks the operator acknowledges bypassing.
    """

    operator: str
    confirmed: bool
    acknowledged_items: frozenset[DryRunCheck] = field(default_factory=frozenset)

    def covers(self, verdict: DryRunVerdict) -> bool:
        """Whether this confirmation validly acknowledges all of a verdict's items.

        Args:
            verdict: The failing verdict being overridden.

        Returns:
            (bool) True only when confirmed, operator-named, and acknowledging every
            violated check.
        """
        if not self.confirmed or not self.operator:
            return False
        return set(verdict.items_hit()).issubset(self.acknowledged_items)


@dataclass(frozen=True)
class TransmissionGrant:
    """The sole token authorising real-robot transmission after a dry-run.

    Cannot be constructed outside ``interlock`` — ``__init__`` requires the module's
    private key — so real transmission can only be authorised through this module's
    two sanctioned mints.

    Attributes:
        verdict: The dry-run verdict this grant was issued against.
        via_modal_confirm: Whether the grant was issued through the modal-confirm
            bypass (True) or a clean passing verdict (False).
        operator: The confirming operator when bypassed, else empty.
    """

    verdict: DryRunVerdict
    via_modal_confirm: bool
    operator: str

    def __init__(
        self,
        key: object,
        verdict: DryRunVerdict,
        via_modal_confirm: bool,
        operator: str,
    ) -> None:
        """Construct a grant; refuses any caller not holding the interlock's key."""
        if key is not _GRANT_KEY:
            raise RuntimeError(
                "TransmissionGrant may be minted only by the interlock's sanctioned "
                "authorisers, not fabricated elsewhere (09 FR-SIM-033)"
            )
        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "via_modal_confirm", via_modal_confirm)
        object.__setattr__(self, "operator", operator)


def authorize_transmission(verdict: DryRunVerdict) -> TransmissionGrant:
    """Authorise transmission for a passing verdict; hard-block otherwise.

    This path has no bypass: a verdict with any violation raises. The modal-confirm
    override is a separate, explicit call.

    Args:
        verdict: The dry-run verdict to gate on.

    Returns:
        (TransmissionGrant) A grant, only when the verdict passed.

    Raises:
        HardBlockError: If the verdict carries any violation.
    """
    if not verdict.passed:
        raise HardBlockError(
            f"dry-run failed with {len(verdict.violations)} violation(s) across "
            f"{[check.value for check in verdict.items_hit()]}; real transmission is "
            "hard-blocked (09 FR-SIM-033) — override requires an explicit modal confirm"
        )
    return TransmissionGrant(_GRANT_KEY, verdict, via_modal_confirm=False, operator="")


def authorize_with_modal_confirm(
    verdict: DryRunVerdict, confirmation: ModalConfirmation
) -> TransmissionGrant:
    """The one sanctioned bypass: authorise a failing verdict via modal confirm.

    Args:
        verdict: The dry-run verdict, which may carry violations.
        confirmation: The operator's explicit acknowledgement; must cover every
            violated check.

    Returns:
        (TransmissionGrant) A grant issued through the modal-confirm path.

    Raises:
        HardBlockError: If the confirmation does not validly acknowledge every
            violation.
    """
    if not verdict.passed and not confirmation.covers(verdict):
        raise HardBlockError(
            "modal confirmation does not acknowledge every violated check "
            f"({[check.value for check in verdict.items_hit()]}); refusing to bypass "
            "the hard block (09 FR-SIM-033)"
        )
    return TransmissionGrant(
        _GRANT_KEY, verdict, via_modal_confirm=True, operator=confirmation.operator
    )
