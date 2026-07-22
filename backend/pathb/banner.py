"""The CG-2B-08b banner: path B always shows "friction uncompensated — detection disabled".

The banner is not a notification a console may dismiss; it is a property of the path-B state. 02b
§2.3 requires it shown 상시 (at all times), so this object exposes canonical text and has no hide
or acknowledge path — a `PathBBootstrap` exposes exactly one, for its whole life.
"""

from __future__ import annotations

from backend.pathb.constants import BANNER_DETAIL, BANNER_HEADLINE


class PathBBanner:
    """The always-visible friction-uncompensated / detection-disabled banner.

    Ownership/threading: immutable and stateless — one instance per `PathBBootstrap`, shareable
    and thread-safe because there is nothing to mutate and no way to dismiss it.
    """

    @property
    def headline(self) -> str:
        """The banner headline (FR-SAF-030 detection-disabled + friction-uncompensated)."""
        return BANNER_HEADLINE

    @property
    def detail(self) -> str:
        """The banner detail — the path-B limitation (FR-SIM-034): no low-speed friction knee."""
        return BANNER_DETAIL

    @property
    def visible(self) -> bool:
        """Whether the banner is shown. Always True — path B cannot hide it (02b §2.3)."""
        return True

    def text(self) -> str:
        """Return the full banner text, headline and detail joined for a one-line render."""
        return f"{BANNER_HEADLINE} — {BANNER_DETAIL}"
