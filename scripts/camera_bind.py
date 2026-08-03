"""Bind camera slots to ports, against a preview the operator actually looks at.

The wrist pair is one model with one serial at one resolution, so nothing readable from the
devices says which arm a camera is looking at. `06` FR-CAM-085 records that hazard and files
serial-burning as priority C — not the canonical contract — so what settles it here is the
same thing that settles which arm is on which CAN channel: the operator looks and says.

The procedure is three commands and no udev rule:

  --list      what is plugged in, and what the stored binding resolves to
  --preview   grab one frame per camera into a directory and name the files by port
  --bind      write slot=port pairs, refusing any port no camera is on right now

`--bind` refuses a port that is not present rather than accepting it for later, because a
binding is only worth what the operator confirmed, and nobody confirms a camera that is not
plugged in.

Operator-facing strings are Korean; this is the surface the person at the bench reads.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from backend.camera.portbinding import (
    CameraBinding,
    CameraBindingError,
    binding_path,
    check_binding,
    load_binding,
    save_binding,
)
from backend.camera.portpath import CaptureNode, enumerate_capture_nodes
from backend.config.store import default_config_directory

# Frames discarded before the keeper so auto-exposure and white balance have settled. A first
# frame off a just-opened UVC camera is routinely black, and a black preview tells the operator
# nothing about which arm it is looking at.
PREVIEW_WARMUP_FRAMES = 12

# JPEG quality for a preview. High enough that the operator can recognise the scene; this is a
# frame to look at once, not a recording.
PREVIEW_JPEG_QUALITY = 92

# Where `--preview` writes when the caller names no directory.
DEFAULT_PREVIEW_DIRNAME = "camera_preview"

EXIT_OK = 0
EXIT_REFUSED = 1


class BindRefusedError(Exception):
    """The operator's request cannot be carried out as asked."""


@dataclass(frozen=True)
class PreviewResult:
    """One camera's preview attempt.

    Attributes:
        node: The camera it was taken from.
        path: Where the frame was written, or None when no frame arrived.
        detail: What happened, for the operator.
    """

    node: CaptureNode
    path: Path | None
    detail: str


def _safe_name(port_path: str) -> str:
    """Return a port path as a filename component.

    The port carries `:` and `/`, which are a drive separator and a path separator on the
    platforms an operator may copy these files to.
    """
    return "".join(character if character.isalnum() else "_" for character in port_path)


def grab_preview(node: CaptureNode, directory: Path) -> PreviewResult:
    """Grab one frame from a camera and write it, labelled with its port.

    The label is burned into the image rather than left to the filename alone: an operator
    comparing two frames side by side is looking at the pictures, and a filename that has
    scrolled off is not part of the comparison.

    Args:
        node: The camera to read.
        directory: Where to write the frame.

    Returns:
        (PreviewResult) Where the frame landed, or why none did. A camera that will not open is
        reported rather than raised on — the other cameras still need previewing.
    """
    import cv2

    directory.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(node.device), cv2.CAP_V4L2)
    try:
        if not capture.isOpened():
            return PreviewResult(node, None, "열리지 않는다 — 다른 프로세스가 잡고 있을 수 있다")
        for _ in range(PREVIEW_WARMUP_FRAMES):
            capture.read()
        arrived, frame = capture.read()
    finally:
        capture.release()

    if not arrived or frame is None:
        return PreviewResult(node, None, "열렸지만 프레임이 오지 않는다")

    label = f"{node.device.name}  {node.port_path}"
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 42), (0, 0, 0), -1)
    cv2.putText(frame, label, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    path = directory / f"{_safe_name(node.port_path)}.jpg"
    cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_JPEG_QUALITY])
    return PreviewResult(node, path, f"{frame.shape[1]}x{frame.shape[0]}")


def parse_slot_pairs(pairs: list[str]) -> dict[str, str]:
    """Parse `slot=port` arguments.

    Args:
        pairs: The raw `slot=port` strings.

    Returns:
        (dict[str, str]) Slot to port.

    Raises:
        BindRefusedError: On a malformed pair, or a slot named twice — a duplicate silently
            keeps the last one, and the operator who typed both would never learn which won.
    """
    slots: dict[str, str] = {}
    for pair in pairs:
        slot, separator, port = pair.partition("=")
        if not separator or not slot.strip() or not port.strip():
            raise BindRefusedError(f"{pair!r} 는 slot=port 형태가 아니다")
        if slot.strip() in slots:
            raise BindRefusedError(f"슬롯 {slot.strip()!r} 이 두 번 지정됐다")
        slots[slot.strip()] = port.strip()
    return slots


def assert_ports_are_present(slots: dict[str, str], present: tuple[CaptureNode, ...]) -> None:
    """Refuse a binding to a port no camera is on right now.

    Args:
        slots: The slot-to-port pairs the operator asked for.
        present: The cameras enumerated this run.

    Raises:
        BindRefusedError: If any named port carries no camera. A binding is worth what the
            operator confirmed against a preview, and an absent camera was not confirmed.
    """
    available = {node.port_path for node in present}
    absent = sorted(port for port in slots.values() if port not in available)
    if absent:
        seen = ", ".join(sorted(available)) or "없음"
        raise BindRefusedError(
            f"이 포트에는 지금 카메라가 없다: {', '.join(absent)}. 현재 포트: {seen}. "
            "프리뷰로 확인하지 않은 카메라는 묶지 않는다"
        )


def render_listing(present: tuple[CaptureNode, ...], binding: CameraBinding | None) -> str:
    """Render what is plugged in and what the stored binding makes of it."""
    lines = [f"카메라 {len(present)}대"]
    claimed = {port: slot for slot, port in (binding.slots if binding else {}).items()}
    for node in present:
        slot = claimed.get(node.port_path)
        marker = f"[{slot}]" if slot else "[미지정]"
        lines.append(f"  {marker:14s} {node.device}  {node.port_path}  {node.card}")
    if binding is None:
        lines.append("저장된 바인딩이 없다 — --preview 로 보고 --bind 로 묶는다")
        return "\n".join(lines)
    check = check_binding(binding, present)
    for slot in check.missing:
        lines.append(f"  [없음]         {slot} → {binding.slots[slot]} (이 포트에 카메라가 없다)")
    lines.append(
        "바인딩 전부 해소됨" if check.ok else "바인딩이 해소되지 않는다 — 다시 묶어야 한다"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the camera binding tool.

    Returns:
        (int) 0 when the request was carried out, 1 when it was refused.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="지금 붙은 카메라와 바인딩 상태")
    parser.add_argument("--preview", action="store_true", help="카메라마다 한 프레임씩 저장")
    parser.add_argument("--preview-dir", type=Path, help="프리뷰를 쓸 디렉터리")
    parser.add_argument(
        "--bind",
        action="append",
        default=[],
        metavar="SLOT=PORT",
        help="슬롯을 포트에 묶는다. 여러 번 줄 수 있다",
    )
    parser.add_argument("--config-dir", type=Path, help="바인딩을 읽고 쓸 디렉터리")
    arguments = parser.parse_args(argv)

    directory = arguments.config_dir or default_config_directory()
    path = binding_path(directory)
    present = enumerate_capture_nodes()

    try:
        stored = load_binding(path)
    except CameraBindingError as refusal:
        print(f"거부: {refusal}", file=sys.stderr)
        return EXIT_REFUSED

    if arguments.bind:
        try:
            slots = parse_slot_pairs(arguments.bind)
            assert_ports_are_present(slots, present)
        except BindRefusedError as refusal:
            print(f"거부: {refusal}", file=sys.stderr)
            return EXIT_REFUSED
        save_binding(path, CameraBinding(slots=slots))
        print(f"{path} 에 기록했다")
        stored = CameraBinding(slots=slots)

    if arguments.preview:
        target = arguments.preview_dir or (directory / DEFAULT_PREVIEW_DIRNAME)
        for result in (grab_preview(node, target) for node in present):
            where = result.path if result.path is not None else "—"
            print(f"  {result.node.port_path}  {result.detail}  {where}")

    if arguments.list or not (arguments.bind or arguments.preview):
        print(render_listing(present, stored))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
