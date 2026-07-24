"""Process- and queue-level constants for the training orchestrator (WP-4A-01).

Values that carry a decision live here so a reader finds the one place a timeout,
a signal choice, or an exit-code meaning is set. Domain layout constants that
describe LeRobot's on-disk checkpoint tree live in `checkpoints.py` instead — a
different responsibility, a different file.
"""

from __future__ import annotations

import signal

# FR-TRN-032: cancellation is a graceful stop, so the trainer receives SIGTERM and
# is given the chance to flush its last checkpoint — never SIGKILL, which would
# lose the in-flight checkpoint the acceptance requires to survive.
TERMINATION_SIGNAL = signal.SIGTERM

# `10` §4.2: an OOM-killed run surfaces as exit 137 (128 + SIGKILL) when a shell
# reports it; a directly-spawned child killed by SIGKILL reports returncode -9.
# Both mean the same crash class, so the classifier folds them together.
OOM_SHELL_EXIT_CODE = 137
SIGKILL_RETURNCODE = -int(signal.SIGKILL)

# The env var CUDA reads to pin a process to a GPU subset. Setting it per child is
# the second half of the exclusivity guard: the ledger reserves a GPU id, and this
# makes the launched trainer actually see only that id (FR-TRN-028).
CUDA_DEVICES_ENV = "CUDA_VISIBLE_DEVICES"

# A cancelled or completed child must have drained its log pipe before the job is
# declared finished, or "logs queryable after job end" (FR-TRN-029) races the
# reader thread. These bound the joins; they are generous because they gate
# correctness, not latency, and a real trainer's final flush is not instant.
PROCESS_WAIT_TIMEOUT_S = 30.0
LOG_READER_JOIN_TIMEOUT_S = 10.0

# One log line at a time is teed to disk; a line-buffered pipe read is the unit.
LOG_FILE_SUFFIX = ".log"

# The three ways out of "resume=false but output_dir already exists" (FR-TRN-016).
# The orchestrator presents these instead of letting LeRobot's validate() raise a
# raw FileExistsError at the user (`10` §4.2, train.py:236-240).
CHOICE_OVERWRITE = "overwrite"
CHOICE_NEW_DIR = "new_dir"
CHOICE_RESUME = "resume"
OUTPUT_DIR_CHOICES = (CHOICE_OVERWRITE, CHOICE_NEW_DIR, CHOICE_RESUME)
