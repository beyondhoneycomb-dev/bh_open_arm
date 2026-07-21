"""Acceptance ⑥ — the txqueuelen setup artifact carries the recommended value (1000).

FR-SYS-011 recommends raising txqueuelen from the kernel default (10) to 1000, and asks
that the setup artifact carry it. The artifact is guidance the operator runs; code does
not set the link. This checks the recommended value is present as both the structured
field and the rendered text.
"""

from __future__ import annotations

from backend.can.link import build_setup_artifact
from backend.can.link.constants import RECOMMENDED_TXQUEUELEN


def test_setup_artifact_contains_recommended_txqueuelen() -> None:
    """The recommended value 1000 is present as field and in the rendered document."""
    artifact = build_setup_artifact(["can0", "can1"])

    assert RECOMMENDED_TXQUEUELEN == 1000
    assert artifact.recommended_txqueuelen == 1000

    rendered = artifact.render()
    assert "txqueuelen" in rendered
    assert "1000" in rendered
    for iface in ("can0", "can1"):
        assert f"ip link set {iface} txqueuelen 1000" in rendered
