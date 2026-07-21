"""Data model for the CTR-OWN@v1 file/module ownership view.

An ownership claim binds one work package to one path glob for one *span* — a
half-open ordinal interval on that glob's ownership timeline. The span is the
dimension the registry's `owns[]` axis lacks: `owns[]` records *who* owns a glob,
never *when*. `06` §3.2 encodes the *when* as handover arrows (`WP-1-02 →
WP-1-03`); this model turns those arrows into comparable intervals so that
"concurrent ownership" and "sequential handover" become a decidable interval
question rather than a hand-read of prose.

The forbidden condition is concurrent ownership: two exclusive claims on the
same real file whose spans overlap. A sequential handover — adjacent spans that
share only their boundary point — is permitted, because a half-open interval
excludes its end (`02` §2.0.4: the `OpenArmFollower` subclass is handed from
`WP-1-02` to `WP-1-03`, and is never held by both at once).
"""

from __future__ import annotations

from dataclasses import dataclass

# A single owner over the whole timeline occupies the unit interval [0, 1). A
# handover chain lays its members end to end from this origin, one unit each.
SPAN_ORIGIN = 0
SPAN_UNIT = 1


@dataclass(frozen=True)
class Span:
    """A half-open ownership interval `[start, end)` on one glob's timeline.

    Half-open is the whole point: two adjacent spans `[0, 1)` and `[1, 2)` share
    only the boundary point `1`, which belongs to neither, so a sequential
    handover does not read as an overlap. Two spans that share any interior point
    do overlap, which is the concurrent-ownership condition the checker rejects.

    Attributes:
        start: Inclusive lower bound.
        end: Exclusive upper bound; must be strictly greater than `start`.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"span end {self.end} must exceed start {self.start}")

    def overlaps(self, other: Span) -> bool:
        """Report whether two spans share an interior point.

        Args:
            other: The span to compare against.

        Returns:
            (bool) True when the half-open intervals intersect.
        """
        return self.start < other.end and other.start < self.end

    def label(self) -> str:
        """Render the span as a report token.

        Returns:
            (str) The half-open interval in `[start, end)` form.
        """
        return f"[{self.start}, {self.end})"


@dataclass(frozen=True)
class Claim:
    """One row of the CTR-OWN@v1 view: a package owns a glob for a span.

    These are the five fields `02a` §3.2 names for the registry
    (`{path_glob, 소유 WP, 배타 여부, 소유 구간, 동시 편집 금지 목록}`) with the
    concurrent-edit-forbidden list lifted out to `Conflict`, since it is a
    relation between two claims rather than a property of one.

    Attributes:
        path_glob: The ownership glob, exactly as the registry `owns[]` axis
            spells it.
        owner_wp: The `WP-*` that owns the glob during `span`.
        exclusive: True when the mode forbids concurrent ownership
            (`EXCLUSIVE` or the pre-freeze phase of `CONTRACT_FROZEN`).
        span: The half-open interval this package owns the glob for.
    """

    path_glob: str
    owner_wp: str
    exclusive: bool
    span: Span


@dataclass(frozen=True)
class Conflict:
    """A rejected pair: two exclusive claims that own one real file at one time.

    This is the materialised "동시 편집 금지 목록" (concurrent-edit-forbidden
    list) entry — proof that spans overlap is not enough, so the shared real
    files are carried too, because two globs that never expand to a common file
    are not in conflict however their spans sit.

    Attributes:
        left_wp: One owning package.
        right_wp: The other owning package.
        left_glob: The glob `left_wp` claims.
        right_glob: The glob `right_wp` claims.
        shared_paths: Real files both globs expand to; never empty.
    """

    left_wp: str
    right_wp: str
    left_glob: str
    right_glob: str
    shared_paths: tuple[str, ...]

    def as_line(self) -> str:
        """Render the conflict as one report line.

        Returns:
            (str) Single-line human-readable form naming the shared files.
        """
        shown = ", ".join(self.shared_paths[:4])
        return (
            f"{self.left_wp} vs {self.right_wp} concurrently own "
            f"{len(self.shared_paths)} shared path(s): {shown}"
        )
