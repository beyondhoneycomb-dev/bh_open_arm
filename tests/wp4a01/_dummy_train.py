"""A stand-in for `lerobot-train` used by the WP-4A-01 acceptance tests.

The orchestrator launches this exactly as it would launch `lerobot-train` — same
`build_argv`, same `--config_path/--resume` flags, same subprocess spawn — so the
tests exercise the real launch path, never a mock. What this script fakes is only
the training itself: it advances a step counter, writes checkpoints in LeRobot's
on-disk layout, and models LeRobot's resume semantics (restore step + optimizer +
scheduler from the last checkpoint and CONTINUE). No GPU, no torch, no real work.

It is self-contained on purpose. It runs in a fresh subprocess whose sys.path need
not contain the repo, so it duplicates the small set of layout strings from
`backend.training.orchestrator.checkpoints` rather than importing them. The strings
are LeRobot's own checkpoint contract (lerobot.utils.constants), stable across the
pin.

Modes:
- fresh (`--resume=false`): step 0 -> `--steps`, checkpointing on `--save_freq`.
- resume (`--resume=true --config_path=<ckpt>/train_config.json`): read steps from
  that config and the current step/optimizer/scheduler from `checkpoints/last`,
  then CONTINUE — the step counter does not restart.
- hold (`--hold_at_step=N`): on reaching step N, write a checkpoint and block until
  SIGTERM, which writes a final checkpoint at the current step and exits cleanly.
  This is how a test parks a job on a GPU (exclusivity) or at a known step (cancel).
"""

from __future__ import annotations

import argparse
import json
import signal
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

CHECKPOINTS_DIR = "checkpoints"
LAST_CHECKPOINT_LINK = "last"
PRETRAINED_MODEL_DIR = "pretrained_model"
TRAINING_STATE_DIR = "training_state"
TRAINING_STEP_FILE = "training_step.json"
TRAIN_CONFIG_NAME = "train_config.json"
OPTIMIZER_STATE_FILE = "optimizer_state.json"
SCHEDULER_STATE_FILE = "scheduler_state.json"
FAKE_MODEL_FILE = "model.fake"

_MIN_STEP_DIGITS = 6
_LR_PER_STEP = 0.01


@dataclass
class TrainState:
    """The mutable run state the loop advances and the SIGTERM handler flushes."""

    output_dir: Path
    steps: int
    save_freq: int
    step: int
    total_updates: int


def _step_identifier(step: int, total_steps: int) -> str:
    """Zero-pad a step the way LeRobot names checkpoint directories."""
    digits = max(_MIN_STEP_DIGITS, len(str(total_steps)))
    return f"{step:0{digits}d}"


def _write_checkpoint(state: TrainState) -> Path:
    """Write a checkpoint at the current step in LeRobot's layout, update `last`.

    Returns:
        (Path) The checkpoint step directory.
    """
    root = state.output_dir / CHECKPOINTS_DIR
    step_dir = root / _step_identifier(state.step, state.steps)
    pretrained = step_dir / PRETRAINED_MODEL_DIR
    training_state = step_dir / TRAINING_STATE_DIR
    pretrained.mkdir(parents=True, exist_ok=True)
    training_state.mkdir(parents=True, exist_ok=True)

    (pretrained / TRAIN_CONFIG_NAME).write_text(
        json.dumps(
            {
                "output_dir": str(state.output_dir),
                "steps": state.steps,
                "save_freq": state.save_freq,
                "resume": False,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (pretrained / FAKE_MODEL_FILE).write_text("fake-weights", encoding="utf-8")
    (training_state / TRAINING_STEP_FILE).write_text(
        json.dumps({"step": state.step}, sort_keys=True), encoding="utf-8"
    )
    (training_state / OPTIMIZER_STATE_FILE).write_text(
        json.dumps({"total_updates": state.total_updates}, sort_keys=True), encoding="utf-8"
    )
    (training_state / SCHEDULER_STATE_FILE).write_text(
        json.dumps({"last_step": state.step, "last_lr": _LR_PER_STEP * state.step}, sort_keys=True),
        encoding="utf-8",
    )

    link = root / LAST_CHECKPOINT_LINK
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(step_dir.name)
    return step_dir


def _restore(output_dir: Path, config_path: Path) -> TrainState:
    """Rebuild run state from a checkpoint, modelling LeRobot's resume.

    Reads `steps`/`save_freq` from the checkpoint's train_config.json (what
    `--config_path` points at) and the step/optimizer from `checkpoints/last`, so
    the resumed run continues rather than restarts.

    Args:
        output_dir: The run output directory.
        config_path: The `train_config.json` passed via `--config_path`.

    Returns:
        (TrainState) State positioned at the checkpoint's step.
    """
    if not config_path.is_file():
        print(f"resume config_path does not exist: {config_path}", flush=True)
        raise SystemExit(2)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    link = output_dir / CHECKPOINTS_DIR / LAST_CHECKPOINT_LINK
    training_state = link.resolve() / TRAINING_STATE_DIR
    step = json.loads((training_state / TRAINING_STEP_FILE).read_text(encoding="utf-8"))["step"]
    optimizer = json.loads((training_state / OPTIMIZER_STATE_FILE).read_text(encoding="utf-8"))
    return TrainState(
        output_dir=output_dir,
        steps=int(config["steps"]),
        save_freq=int(config["save_freq"]),
        step=int(step),
        total_updates=int(optimizer["total_updates"]),
    )


def _install_term_handler(state: TrainState) -> None:
    """Install a SIGTERM handler that flushes a final checkpoint then exits 0.

    FR-TRN-032's "취소 시 마지막 체크포인트 보존": a cancel arrives as SIGTERM, and
    the last thing the trainer does is write a checkpoint at the step it reached.
    """

    def handle_term(signum: int, frame: FrameType | None) -> None:
        _write_checkpoint(state)
        print(f"terminated step={state.step}", flush=True)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_term)


def _wait_for_term() -> None:
    """Block until SIGTERM arrives (the handler exits the process)."""
    while True:
        signal.pause()


def _run(state: TrainState, hold_at_step: int) -> None:
    """Advance the step counter, checkpointing and optionally holding.

    Args:
        state: The run state to advance.
        hold_at_step: Step to park at until SIGTERM, or a negative value for none.
    """
    if hold_at_step >= 0 and state.step == hold_at_step:
        _write_checkpoint(state)
        print(f"held step={state.step}", flush=True)
        _wait_for_term()

    for step in range(state.step + 1, state.steps + 1):
        state.step = step
        state.total_updates += 1
        if state.save_freq > 0 and (step % state.save_freq == 0 or step == state.steps):
            _write_checkpoint(state)
        print(f"step={step} total_updates={state.total_updates}", flush=True)
        if hold_at_step >= 0 and step == hold_at_step:
            _write_checkpoint(state)
            print(f"held step={state.step}", flush=True)
            _wait_for_term()

    if state.step >= state.steps:
        _write_checkpoint(state)
    print(f"done step={state.step}", flush=True)


def _parse_bool(value: str) -> bool:
    """Parse a draccus-style boolean flag value."""
    return value.strip().lower() == "true"


def main(argv: list[str] | None = None) -> int:
    """Run the dummy trainer.

    Returns:
        (int) 0 on completion; the SIGTERM handler exits 0 on cancel.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--steps", type=int, default=0)
    parser.add_argument("--save_freq", type=int, default=1)
    parser.add_argument("--hold_at_step", type=int, default=-1)
    parser.add_argument("--resume", default="false")
    parser.add_argument("--config_path", default="")
    # The orchestrator also passes --dataset.* flags; they are not this fake's
    # concern, so unknown flags are ignored rather than rejected.
    args, _ignored = parser.parse_known_args(argv)

    output_dir = Path(args.output_dir)
    if _parse_bool(args.resume):
        state = _restore(output_dir, Path(args.config_path))
    else:
        state = TrainState(
            output_dir=output_dir,
            steps=args.steps,
            save_freq=args.save_freq,
            step=0,
            total_updates=0,
        )

    _install_term_handler(state)
    _run(state, args.hold_at_step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
