"""The binding tool's refusals, over a stated camera set rather than whatever is plugged in.

The preview half needs a camera and is not exercised here; what these cases hold is the part
that decides whether an operator's answer is written at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.camera.portbinding import FIELD_SLOTS, binding_path
from backend.camera.portpath import CaptureNode
from scripts import camera_bind

WRIST_LEFT_PORT = "usb-0000:00:0d.0-1.1.3.3"
WRIST_RIGHT_PORT = "usb-0000:00:0d.0-1.1.4"
ABSENT_PORT = "usb-0000:99:99.9-9.9"

ARDUCAM_CARD = "Arducam B0495 (USB3 2.3MP)"


def _present() -> tuple[CaptureNode, ...]:
    """The wrist pair, on the two ports it sits on."""
    return (
        CaptureNode(device=Path("/dev/video0"), port_path=WRIST_LEFT_PORT, card=ARDUCAM_CARD),
        CaptureNode(device=Path("/dev/video2"), port_path=WRIST_RIGHT_PORT, card=ARDUCAM_CARD),
    )


def _no_cameras(monkeypatch: pytest.MonkeyPatch, present: tuple[CaptureNode, ...]) -> None:
    """Answer enumeration with a stated camera set, so no case depends on this host."""
    monkeypatch.setattr(camera_bind, "enumerate_capture_nodes", lambda: present)


def test_a_pair_is_parsed_into_a_slot_and_a_port() -> None:
    assert camera_bind.parse_slot_pairs([f"wrist_left={WRIST_LEFT_PORT}"]) == {
        "wrist_left": WRIST_LEFT_PORT
    }


def test_a_pair_with_no_separator_is_refused() -> None:
    with pytest.raises(camera_bind.BindRefusedError, match="slot=port"):
        camera_bind.parse_slot_pairs(["wrist_left"])


def test_a_pair_with_an_empty_side_is_refused() -> None:
    with pytest.raises(camera_bind.BindRefusedError, match="slot=port"):
        camera_bind.parse_slot_pairs(["wrist_left="])


def test_a_slot_named_twice_is_refused_rather_than_silently_taking_the_last() -> None:
    """Both were typed on purpose; keeping one silently is the operator's answer being lost."""
    pairs = [f"wrist={WRIST_LEFT_PORT}", f"wrist={WRIST_RIGHT_PORT}"]

    with pytest.raises(camera_bind.BindRefusedError, match="두 번"):
        camera_bind.parse_slot_pairs(pairs)


def test_binding_to_a_port_with_no_camera_is_refused() -> None:
    with pytest.raises(camera_bind.BindRefusedError, match=ABSENT_PORT):
        camera_bind.assert_ports_are_present({"wrist_left": ABSENT_PORT}, _present())


def test_binding_to_a_present_port_is_admitted() -> None:
    camera_bind.assert_ports_are_present({"wrist_left": WRIST_LEFT_PORT}, _present())


def test_a_written_binding_names_the_ports_the_operator_gave(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_cameras(monkeypatch, _present())

    code = camera_bind.main(
        [
            "--bind",
            f"wrist_left={WRIST_LEFT_PORT}",
            "--bind",
            f"wrist_right={WRIST_RIGHT_PORT}",
            "--config-dir",
            str(tmp_path),
        ]
    )

    assert code == camera_bind.EXIT_OK
    written = json.loads(binding_path(tmp_path).read_text(encoding="utf-8"))
    assert written[FIELD_SLOTS] == {
        "wrist_left": WRIST_LEFT_PORT,
        "wrist_right": WRIST_RIGHT_PORT,
    }


def test_a_refused_bind_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A refusal that still wrote would leave the rig bound to a camera nobody confirmed."""
    _no_cameras(monkeypatch, _present())

    code = camera_bind.main(["--bind", f"wrist_left={ABSENT_PORT}", "--config-dir", str(tmp_path)])

    assert code == camera_bind.EXIT_REFUSED
    assert not binding_path(tmp_path).exists()


def test_a_rebind_replaces_the_previous_answer_rather_than_merging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A merge would leave a slot from an older layout bound to a camera nobody just looked at."""
    _no_cameras(monkeypatch, _present())
    camera_bind.main(["--bind", f"scene={WRIST_LEFT_PORT}", "--config-dir", str(tmp_path)])

    camera_bind.main(["--bind", f"wrist_left={WRIST_LEFT_PORT}", "--config-dir", str(tmp_path)])

    written = json.loads(binding_path(tmp_path).read_text(encoding="utf-8"))
    assert written[FIELD_SLOTS] == {"wrist_left": WRIST_LEFT_PORT}


def test_the_listing_names_every_present_camera_and_its_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _no_cameras(monkeypatch, _present())

    camera_bind.main(["--list", "--config-dir", str(tmp_path)])

    printed = capsys.readouterr().out
    assert WRIST_LEFT_PORT in printed
    assert WRIST_RIGHT_PORT in printed


def test_the_listing_says_a_bound_camera_is_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The operator needs the slot named, not a count that still adds up."""
    _no_cameras(monkeypatch, _present())
    camera_bind.main(["--bind", f"wrist_right={WRIST_RIGHT_PORT}", "--config-dir", str(tmp_path)])

    _no_cameras(monkeypatch, _present()[:1])
    camera_bind.main(["--list", "--config-dir", str(tmp_path)])

    printed = capsys.readouterr().out
    assert "wrist_right" in printed
    assert "해소되지 않는다" in printed


def test_a_corrupt_stored_binding_is_refused_rather_than_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_cameras(monkeypatch, _present())
    binding_path(tmp_path).write_text("{not json", encoding="utf-8")

    assert camera_bind.main(["--list", "--config-dir", str(tmp_path)]) == camera_bind.EXIT_REFUSED
