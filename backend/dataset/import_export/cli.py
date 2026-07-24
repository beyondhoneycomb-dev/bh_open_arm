"""A thin `openarm-dataset-convert`-shaped entry that routes through the guard.

The reference CLI (`convert.py:35-40`) offers `--format {openarm, lerobot_v2.1,
lerobot_v3.0, gr00t}` and takes an input path it always opens as OpenArm. This entry
mirrors that surface but enforces the WP-3D-07 policy: only a legacy OpenArm ->
`lerobot_v3.0` import is authorized, and a `gr00t`/`lerobot_v2.1` output (or a LeRobot
input) is refused with a non-zero exit. It composes — but does not run — the isolated
invocation, because the converter itself lives in a separate environment (`FR-DAT-040`).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from backend.dataset.import_export.constants import CONVERT_TOOL, CONVERTER_FORMAT_CHOICES
from backend.dataset.import_export.formats import InputKind
from backend.dataset.import_export.guard import (
    ConversionRefusedError,
    ConversionRequest,
    authorize_conversion,
    plan_import,
)

EXIT_OK = 0
EXIT_REFUSED = 2


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser mirroring the reference converter surface.

    Returns:
        (argparse.ArgumentParser) The parser.
    """
    parser = argparse.ArgumentParser(
        prog=CONVERT_TOOL,
        description="Legacy OpenArm -> LeRobot v3.0 import (the only authorized use).",
    )
    parser.add_argument("input", help="input dataset path")
    parser.add_argument("output", help="output dataset path")
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=list(CONVERTER_FORMAT_CHOICES),
        default="openarm",
        help="output format; only lerobot_v3.0 is authorized here",
    )
    parser.add_argument(
        "--input-kind",
        choices=[kind.value for kind in InputKind],
        default=InputKind.LEGACY_OPENARM.value,
        help="what the input dataset is; only legacy_openarm can be opened",
    )
    parser.add_argument("--fps", type=int, default=30, help="frame rate for the imported grid")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Route a conversion request through the guard and report the verdict.

    Args:
        argv: The command-line arguments; defaults to `sys.argv[1:]`.

    Returns:
        (int) `EXIT_OK` when a legacy import is authorized and planned, `EXIT_REFUSED`
            when the request is refused.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    request = ConversionRequest(
        input_kind=InputKind(args.input_kind),
        output_format=args.output_format,
    )
    try:
        authorize_conversion(request)
    except ConversionRefusedError as refused:
        print(f"{CONVERT_TOOL}: refused: {refused}", file=sys.stderr)
        return EXIT_REFUSED

    invocation = plan_import(args.input, args.output, args.fps)
    print(f"{CONVERT_TOOL}: authorized legacy import")
    print(f"  isolated env: {invocation.env_extra}")
    print(f"  argv: {' '.join(invocation.argv)}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
