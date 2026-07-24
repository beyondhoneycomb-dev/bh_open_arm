"""The three inference backends the engine factory selects between (`FR-INF-015`/`019`).

`11` §3.3 fixes the set to exactly three, and the plan (`02c` §1.7 대가) keeps all
three rather than two: dropping the remote path would leave no way to satisfy
`FR-INF-034` (Orin + GR00T = 4.6 Hz → `sync` blocked, RTC or async chunking
required), which kills the Jetson Orin target. So the enum is closed at three and a
value outside it is a construction error, not a silently-accepted fourth mode.

- `SYNC`  — inline, one policy call per control tick (`lerobot` `SyncInferenceEngine`).
- `RTC`   — Real-Time Chunking: async chunk generation with a refill low-watermark.
- `REMOTE_GRPC` — `policy_server` + `robot_client`, where the client calls
  `robot.send_action()` directly (`robot_client.py:381-383`), so the safety gateway
  is the `send_action` override, not a pipeline step (`NFR-INF-008`).
"""

from __future__ import annotations

from enum import Enum


class InferenceBackend(Enum):
    """The closed set of inference backends (`InferenceBackend ∈ {SYNC, RTC, REMOTE_GRPC}`).

    Membership is the contract: the factory dispatches on exactly these, and a
    caller cannot introduce a fourth backend without a code change that this enum
    forces through review.
    """

    SYNC = "sync"
    RTC = "rtc"
    REMOTE_GRPC = "remote_grpc"

    @property
    def is_in_process(self) -> bool:
        """Whether this backend runs inference in-process and publishes to the mailbox.

        Returns:
            (bool) True for `SYNC`/`RTC` (mailbox publishers); False for `REMOTE_GRPC`,
            whose client calls `send_action()` directly (`NFR-INF-008`).
        """
        return self in (InferenceBackend.SYNC, InferenceBackend.RTC)
