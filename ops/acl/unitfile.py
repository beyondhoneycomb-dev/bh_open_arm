"""A small systemd unit-file reader, only as much as the ACL checks need.

The static checks read the *installed text*, because that is the artifact the kernel
loads and the exact thing the acceptance fixtures are — not a Python model of it. This
parser therefore preserves the two systemd semantics a naive `key=value` split would get
wrong, both of which fail silently:

- A directive may be **repeated**, and for the list-valued ones (`RestrictAddressFamilies`,
  `DeviceAllow`, `ReadWritePaths`) systemd *appends* across the repeats rather than letting
  the last line win. Collapsing repeats to a single value would drop admitted families.
- An **empty assignment** (`RestrictAddressFamilies=`) is not "set to blank"; it *resets*
  the accumulated list. A checker that treated it as a value would see a phantom empty
  entry and miss that the list was cleared.

Anything else (quoting rules, specifier expansion) is out of scope: the shipped units use
none of it, and inventing support for what no artifact exercises is untested surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UnitFile:
    """A parsed unit file: section to directive key to the values assigned, in order.

    Empty-assignment resets are already applied, so `assignments[section][key]` holds
    exactly the values in effect, in file order. A key present but reset to nothing maps
    to an empty list; a key never mentioned is absent from the map.

    Attributes:
        assignments: `section -> key -> [effective values in order]`.
    """

    assignments: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def has(self, section: str, key: str) -> bool:
        """Whether a directive was assigned at all, even if later reset to empty.

        Presence is what "the directive is in the file" means for the acceptance ④
        directive-presence scan; an empty reset still counts as the author having
        addressed the directive.

        Args:
            section: Section name without brackets.
            key: Directive name.

        Returns:
            (bool) True when the key appears in the section.
        """
        return key in self.assignments.get(section, {})

    def values(self, section: str, key: str) -> list[str]:
        """The effective values of a directive, in file order.

        Args:
            section: Section name without brackets.
            key: Directive name.

        Returns:
            (list[str]) Values in effect; empty when absent or reset to nothing.
        """
        return list(self.assignments.get(section, {}).get(key, []))

    def scalar(self, section: str, key: str) -> str | None:
        """The last value of a directive, for the scalar (last-wins) directives.

        Args:
            section: Section name without brackets.
            key: Directive name.

        Returns:
            (str | None) The final value, or None when absent or reset to nothing.
        """
        values = self.values(section, key)
        return values[-1] if values else None


def _fold_continuations(text: str) -> list[str]:
    """Join backslash-continued physical lines into logical lines.

    Args:
        text: Unit file body.

    Returns:
        (list[str]) Logical lines with continuations folded.
    """
    logical: list[str] = []
    pending = ""
    for raw in text.splitlines():
        if raw.rstrip().endswith("\\"):
            pending += raw.rstrip()[:-1] + " "
            continue
        logical.append(pending + raw)
        pending = ""
    if pending:
        logical.append(pending)
    return logical


def parse_unit(text: str) -> UnitFile:
    """Parse unit-file text, applying append and empty-reset semantics.

    Args:
        text: Unit file body (a `.service` unit or a `.conf` drop-in).

    Returns:
        (UnitFile) The parsed directives with resets already applied.
    """
    assignments: dict[str, dict[str, list[str]]] = {}
    section = ""
    for line in _fold_continuations(text):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            assignments.setdefault(section, {})
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        bucket = assignments.setdefault(section, {}).setdefault(key, [])
        if value:
            bucket.append(value)
        else:
            bucket.clear()
    return UnitFile(assignments=assignments)
