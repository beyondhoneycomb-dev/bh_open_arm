"""The perturbation-protocol structure (`02c` §3.5 산출: 섭동 프로토콜).

The load-bearing rule of this structure is that the plan does NOT invent perturbation
axes: each axis is derived from the per-task initial-state distribution Wave 3C
recorded (`02c` §3.5 인터페이스 계약 / CG-4C-05c). So a `PerturbationAxis` cannot exist
without naming the distribution it came from — construction refuses an axis whose
`distribution_ref` is empty, which is the "0 arbitrary axes" guarantee as code rather
than as a review promise.

Because the Wave 3C initial-state distribution has not landed (its WP is DEFERRED,
Human/HW band), no real axis can be defined yet, so the only protocol this phase can
produce is the DEFERRED one: `PerturbationProtocol.deferred_pending_wave_3c`. Its
`deferred_reason` states, in the report, that the distribution is absent and the
generalization gap is therefore unmeasured (`02c` §3.5 ③ negative branch — a deferral,
not a FAIL). A non-deferred protocol is representable (`of_axes`) so the schema is
complete and the acceptance gates have a positive control, but the current, honest
state of the system is deferred.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.eval.protocol.constants import PERTURBED_DEFERRED_REASON


class PerturbationError(ValueError):
    """Raised when a perturbation axis or protocol violates its schema.

    The cases: an axis with no distribution reference (an arbitrary axis, CG-4C-05c),
    a non-deferred protocol with no axes (a protocol that perturbs nothing), or a
    deferred protocol that nonetheless carries axes (a contradiction — a deferred
    protocol is deferred precisely because no axis can be defined yet).
    """


@dataclass(frozen=True)
class PerturbationAxis:
    """One perturbation axis, derived from a Wave 3C initial-state distribution.

    Frozen because an axis is a definition, not a mutable buffer. The `distribution_ref`
    is mandatory and non-empty: an axis that names no source distribution is exactly the
    "arbitrary axis" CG-4C-05c forbids, so `__post_init__` refuses it at construction.

    Attributes:
        name: The perturbed quantity (e.g. an object's initial x-position). Descriptive
            only; the discipline is carried by `distribution_ref`, not by this name.
        distribution_ref: The Wave 3C initial-state distribution this axis is derived
            from. Non-empty by contract — the reference is what makes the axis principled
            rather than invented (`02c` §3.5, CG-4C-05c).
    """

    name: str
    distribution_ref: str

    def __post_init__(self) -> None:
        """Refuse an axis that references no source distribution (CG-4C-05c).

        Raises:
            PerturbationError: When `name` or `distribution_ref` is blank.
        """
        if not self.name.strip():
            raise PerturbationError("a perturbation axis must have a non-empty name")
        if not self.distribution_ref.strip():
            raise PerturbationError(
                "a perturbation axis must reference the Wave 3C initial-state distribution it is "
                "derived from; an axis with no reference is arbitrary (CG-4C-05c, 02c §3.5)"
            )


@dataclass(frozen=True)
class PerturbationProtocol:
    """The set of perturbation axes for one task, or a deferral pending Wave 3C.

    Frozen. Exactly one of two shapes is well-formed, enforced by `__post_init__`:

    - DEFERRED — `deferred_reason` is non-empty and `axes` is empty. The current phase-1
      state: the Wave 3C distribution has not landed, so no axis can be defined.
    - DEFINED — `deferred_reason` is empty and `axes` is non-empty. Every axis carries
      its Wave 3C reference (guaranteed by `PerturbationAxis` itself).

    Attributes:
        task_id: The task this protocol perturbs.
        axes: The perturbation axes; empty iff the protocol is deferred.
        deferred_reason: Why the protocol is deferred; empty iff it is defined.
    """

    task_id: str
    axes: tuple[PerturbationAxis, ...]
    deferred_reason: str

    def __post_init__(self) -> None:
        """Enforce the deferred-xor-defined shape.

        Raises:
            PerturbationError: When a deferred protocol carries axes, or a defined
                protocol carries none.
        """
        if not self.task_id.strip():
            raise PerturbationError("a perturbation protocol must name its task")
        if self.is_deferred and self.axes:
            raise PerturbationError(
                "a deferred perturbation protocol must carry no axes; it is deferred precisely "
                "because no axis can be defined until the Wave 3C distribution lands"
            )
        if not self.is_deferred and not self.axes:
            raise PerturbationError(
                "a defined perturbation protocol must carry at least one axis; a protocol that "
                "perturbs nothing is not a perturbation"
            )

    @property
    def is_deferred(self) -> bool:
        """Whether this protocol is deferred (no axes definable yet)."""
        return bool(self.deferred_reason.strip())

    @staticmethod
    def deferred_pending_wave_3c(task_id: str) -> PerturbationProtocol:
        """Build the DEFERRED protocol — the honest current state (`02c` §3.5 ③).

        Args:
            task_id: The task whose perturbation is deferred.

        Returns:
            (PerturbationProtocol) A deferred protocol with no axes, whose reason cites
                the missing Wave 3C distribution and the unmeasured gap.
        """
        return PerturbationProtocol(
            task_id=task_id, axes=(), deferred_reason=PERTURBED_DEFERRED_REASON
        )

    @staticmethod
    def of_axes(task_id: str, axes: tuple[PerturbationAxis, ...]) -> PerturbationProtocol:
        """Build a DEFINED protocol from axes (the positive control / post-Wave-3C shape).

        Args:
            task_id: The task this protocol perturbs.
            axes: The Wave-3C-derived axes; must be non-empty.

        Returns:
            (PerturbationProtocol) A defined protocol carrying the axes.

        Raises:
            PerturbationError: When `axes` is empty.
        """
        return PerturbationProtocol(task_id=task_id, axes=axes, deferred_reason="")
