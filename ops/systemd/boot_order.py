"""Boot-order dependency: the backend refuses to start when link bring-up failed.

`01` FR-SYS-006 makes the unit the sole configurer of the link, so the backend depends on
it rather than doing the work itself. Acceptance ③ demands that a *failed* bring-up unit
stops the backend from starting at all — zero silent progress. In systemd that is precisely
`Requires=` **plus** `After=`: `Requires=` propagates the failure (a failed required unit
pulls its dependents down), and `After=` orders the backend behind it so the failure is
already known when the backend would start. `Wants=` is the trap this module exists to
reject — it expresses the same wish but does *not* propagate failure, so a backend that
only `Wants=` the link unit starts anyway onto an unconfigured bus.

This module renders that dependency drop-in and carries the standalone validator that
distinguishes a real gate from the `Wants=`-only near-miss.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from ops.systemd.constants import BACKEND_UNIT, CAN_LINK_UNIT

# Systemd directives that make a dependent fail when the named unit fails. `Wants=` is
# excluded on purpose: it is the one that looks like a dependency but never propagates
# failure, which is the exact silent-progress hole acceptance ③ guards against.
_FAILURE_PROPAGATING_KEYS = ("Requires", "BindsTo")
_ORDERING_KEY = "After"
_ALL_TRACKED_KEYS = (*_FAILURE_PROPAGATING_KEYS, _ORDERING_KEY, "Wants")

_DIRECTIVE = re.compile(r"^(?P<key>[A-Za-z]+)=(?P<value>.*)$")


@dataclass(frozen=True)
class UnitDependencies:
    """The dependency directives a unit declares, one interface each, as sets of unit ids.

    Attributes:
        requires_or_binds: Units named by `Requires=`/`BindsTo=` — a failure in any of
            these pulls this unit down.
        after: Units named by `After=` — this unit is ordered behind them.
        wants: Units named by `Wants=` — wished for, but a failure never propagates.
    """

    requires_or_binds: frozenset[str]
    after: frozenset[str]
    wants: frozenset[str]

    def refuses_startup_on_failure(self, link_unit: str) -> bool:
        """Whether a failure of `link_unit` blocks this unit from starting.

        Both halves are required: failure propagation (`Requires=`/`BindsTo=`) *and*
        ordering (`After=`). A `Requires=` without `After=` lets systemd start the backend
        concurrently with — or before — the link unit, so the failure is not yet visible;
        a `Wants=` provides neither.

        Args:
            link_unit: The bring-up unit the backend must be gated on.

        Returns:
            (bool) True only when the failure both propagates and is ordered-before.
        """
        return link_unit in self.requires_or_binds and link_unit in self.after


def parse_unit_dependencies(unit_body: str) -> UnitDependencies:
    """Parse the dependency directives out of a unit or drop-in body.

    Only the tracked ordering/requirement keys are read, and each may appear more than once
    or list several space-separated units; both forms accumulate. Sections are ignored
    because systemd resolves these keys within `[Unit]` and no other section defines them.

    Args:
        unit_body: A unit or drop-in file body.

    Returns:
        (UnitDependencies) The units named by each tracked directive.
    """
    collected: dict[str, set[str]] = {key: set() for key in _ALL_TRACKED_KEYS}
    for line in unit_body.splitlines():
        match = _DIRECTIVE.match(line.strip())
        if match is None or match.group("key") not in collected:
            continue
        collected[match.group("key")].update(match.group("value").split())
    requires_or_binds: set[str] = set()
    for key in _FAILURE_PROPAGATING_KEYS:
        requires_or_binds |= collected[key]
    return UnitDependencies(
        requires_or_binds=frozenset(requires_or_binds),
        after=frozenset(collected[_ORDERING_KEY]),
        wants=frozenset(collected["Wants"]),
    )


def render_backend_link_dropin(
    link_unit: str = CAN_LINK_UNIT,
    backend_unit: str = BACKEND_UNIT,
) -> str:
    """Render the drop-in that gates the backend on a successful CAN bring-up.

    A drop-in (`<unit>.d/*.conf`) rather than an edit to the backend unit keeps this
    dependency owned here (WP-OPS-02) without WP-OPS-02 rewriting a unit another package
    owns — the ownership split `01` §4.6 draws between the two.

    Args:
        link_unit: The bring-up unit whose failure must block startup.
        backend_unit: The backend unit the drop-in extends, named in a comment for the
            operator installing it under `<backend_unit>.d/`.

    Returns:
        (str) The drop-in body declaring `Requires=` and `After=` on the link unit.
    """
    return (
        f"# Drop-in for {backend_unit} (install under {backend_unit}.d/).\n"
        "# Requires+After gate the backend on a successful CAN bring-up (01 FR-SYS-006 ③).\n"
        "[Unit]\n"
        f"Requires={link_unit}\n"
        f"After={link_unit}\n"
    )


def backend_gated_on_link(unit_bodies: Iterable[str], link_unit: str = CAN_LINK_UNIT) -> bool:
    """Report whether the merged backend units refuse startup on link-unit failure.

    systemd merges a unit and its drop-ins additively, so the dependency may be declared in
    either; the bodies are parsed together and the gate holds if the merge does. This is the
    acceptance ③ predicate — a definition that only `Wants=` the link unit fails it.

    Args:
        unit_bodies: The backend unit body and any drop-ins that apply to it.
        link_unit: The bring-up unit the backend must be gated on.

    Returns:
        (bool) True when the merged definition both propagates and orders the failure.
    """
    merged = "\n".join(unit_bodies)
    return parse_unit_dependencies(merged).refuses_startup_on_failure(link_unit)
