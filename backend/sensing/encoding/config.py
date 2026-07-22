"""Encoder configuration and the record-start settings latch (`02b` §6.2 WP-3B-05).

Two rules the recording path depends on live here:

- `streaming_encoding` is fixed `False` (`15` NFR-PRF-028). The canonical two-stage
  design records lossless originals and transcodes after the episode; adopting the
  `streaming_encoding=True` real-time-encode bypass is the `SUPERSEDED` defect, so a
  `True` value is refused at construction rather than accepted and later regretted.
- Encoder settings freeze once recording begins (`02b` §6.2 WP-3B-05 ④). Changing
  the queue bound or any encoder knob mid-session would apply a different policy to
  frames already on disk; `EncoderSettings` latches on the first episode and refuses
  any reconfigure until recording stops.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.sensing.encoding.constants import (
    ENCODER_QUEUE_MAXSIZE_DEFAULT,
    STREAMING_ENCODING_CANONICAL,
)


class EncoderConfigError(ValueError):
    """Raised when a configuration violates a WP-3B-05 invariant.

    The two invariants: `streaming_encoding` may not be `True` (the `SUPERSEDED`
    bypass), and encoder settings may not change after recording has started.
    """


@dataclass(frozen=True)
class EncoderConfig:
    """The knobs that shape the transcode worker's backpressure and encode policy.

    Attributes:
        encoder_queue_maxsize: The outstanding-transcode threshold above which a
            backpressure warning is raised. Positive; defaults to the upstream 30.
        streaming_encoding: Fixed `False` by contract; a `True` value is refused.
    """

    encoder_queue_maxsize: int = ENCODER_QUEUE_MAXSIZE_DEFAULT
    streaming_encoding: bool = STREAMING_ENCODING_CANONICAL

    def __post_init__(self) -> None:
        """Reject the `streaming_encoding` bypass and a non-positive queue bound."""
        if self.streaming_encoding is not STREAMING_ENCODING_CANONICAL:
            raise EncoderConfigError(
                "streaming_encoding must stay False (NFR-PRF-028 two-stage canon); "
                "streaming_encoding=True is the SUPERSEDED real-time-encode bypass"
            )
        if not isinstance(self.encoder_queue_maxsize, int) or isinstance(
            self.encoder_queue_maxsize, bool
        ):
            raise EncoderConfigError("encoder_queue_maxsize must be an int")
        if self.encoder_queue_maxsize <= 0:
            raise EncoderConfigError(
                f"encoder_queue_maxsize must be > 0, got {self.encoder_queue_maxsize}"
            )


class EncoderSettings:
    """A held `EncoderConfig` that freezes when recording starts (`02b` §6.2 ④).

    Ownership: one instance holds the encoder policy for one collection session.
    `reconfigure` is the only mutation, and it is refused while the recording latch
    is set — a session that has begun writing originals may not switch encode policy
    underneath the frames already on disk.
    """

    def __init__(self, config: EncoderConfig) -> None:
        """Hold an initial config with the recording latch open.

        Args:
            config: The encoder configuration to start the session with.
        """
        self._config = config
        self._recording = False

    @property
    def config(self) -> EncoderConfig:
        """The current encoder configuration."""
        return self._config

    @property
    def recording(self) -> bool:
        """Whether the recording latch is set, freezing reconfiguration."""
        return self._recording

    def start_recording(self) -> None:
        """Latch the settings: from now on reconfiguration is refused."""
        self._recording = True

    def stop_recording(self) -> None:
        """Release the latch so a new session may reconfigure the encoder."""
        self._recording = False

    def reconfigure(self, config: EncoderConfig) -> None:
        """Replace the encoder configuration, unless recording has begun.

        Args:
            config: The replacement configuration.

        Raises:
            EncoderConfigError: If recording has started — settings are frozen for
                the duration of the session (`02b` §6.2 WP-3B-05 ④).
        """
        if self._recording:
            raise EncoderConfigError(
                "encoder settings are frozen after recording has started; "
                "stop recording before reconfiguring (02b §6.2 WP-3B-05 ④)"
            )
        self._config = config
