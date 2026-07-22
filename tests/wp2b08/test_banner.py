"""WP-2B-08 acceptance CG-2B-08b: the "friction uncompensated" banner is always shown.

02b §2.3 requires the banner shown 상시. These tests pin that the banner is a property of the
path-B state — present on every bootstrap, with no hide or acknowledge path — and that its copy
states both facts FR-SAF-030 / FR-SIM-034 require: friction is uncompensated and detection is off.
"""

from __future__ import annotations

from backend.pathb import BANNER_DETAIL, BANNER_HEADLINE, PathBBanner, PathBBootstrap


def test_bootstrap_always_exposes_a_visible_banner(bootstrap: PathBBootstrap) -> None:
    """Every path-B bootstrap carries a banner and it is visible."""
    assert isinstance(bootstrap.banner, PathBBanner)
    assert bootstrap.banner.visible is True


def test_banner_cannot_be_dismissed() -> None:
    """The banner exposes no hide/dismiss/acknowledge path — visibility is not togglable."""
    banner = PathBBanner()
    for method in ("hide", "dismiss", "acknowledge", "close"):
        assert not hasattr(banner, method)


def test_banner_states_friction_uncompensated_and_detection_off() -> None:
    """The banner copy names both the uncompensated friction and the disabled detection."""
    banner = PathBBanner()
    assert "마찰" in banner.headline
    assert "감지" in banner.headline
    assert banner.headline == BANNER_HEADLINE
    assert banner.detail == BANNER_DETAIL


def test_banner_text_joins_headline_and_detail() -> None:
    """The one-line render carries both the headline and the path-B limitation detail."""
    text = PathBBanner().text()
    assert BANNER_HEADLINE in text
    assert BANNER_DETAIL in text
