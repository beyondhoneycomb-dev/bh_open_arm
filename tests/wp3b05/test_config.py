"""WP-3B-05 ②④ — streaming_encoding is fixed False; settings freeze on record start.

`streaming_encoding=False` is canon (`15` NFR-PRF-028): the `True` real-time-encode
bypass is the `SUPERSEDED` defect and is refused at construction, not left to a
runtime toggle. And once recording begins, the encoder configuration is frozen for
the session (`02b` §6.2 WP-3B-05 ④) — a mid-session change would apply a different
policy to frames already on disk.
"""

from __future__ import annotations

import pytest

from backend.sensing.encoding import EncoderConfig, EncoderConfigError, EncoderSettings
from backend.sensing.encoding.constants import STREAMING_ENCODING_CANONICAL


def test_streaming_encoding_defaults_false():
    """The canonical config records originals, not a streamed encode."""
    assert STREAMING_ENCODING_CANONICAL is False
    assert EncoderConfig().streaming_encoding is False


def test_streaming_encoding_true_is_refused():
    """Adopting streaming_encoding=True is the SUPERSEDED bypass and is refused."""
    with pytest.raises(EncoderConfigError, match="SUPERSEDED"):
        EncoderConfig(streaming_encoding=True)


def test_non_positive_queue_bound_is_refused():
    """The backpressure threshold must be a positive queue size."""
    with pytest.raises(EncoderConfigError):
        EncoderConfig(encoder_queue_maxsize=0)


def test_reconfigure_allowed_before_recording():
    """Before recording starts, the encoder settings may still change."""
    settings = EncoderSettings(EncoderConfig(encoder_queue_maxsize=30))
    settings.reconfigure(EncoderConfig(encoder_queue_maxsize=10))
    assert settings.config.encoder_queue_maxsize == 10


def test_reconfigure_blocked_after_recording_starts():
    """Once recording begins the settings are frozen for the session (④)."""
    settings = EncoderSettings(EncoderConfig(encoder_queue_maxsize=30))
    settings.start_recording()
    assert settings.recording is True
    with pytest.raises(EncoderConfigError, match="frozen"):
        settings.reconfigure(EncoderConfig(encoder_queue_maxsize=10))
    assert settings.config.encoder_queue_maxsize == 30


def test_reconfigure_allowed_again_after_recording_stops():
    """A new session may reconfigure once recording has stopped."""
    settings = EncoderSettings(EncoderConfig(encoder_queue_maxsize=30))
    settings.start_recording()
    settings.stop_recording()
    settings.reconfigure(EncoderConfig(encoder_queue_maxsize=5))
    assert settings.config.encoder_queue_maxsize == 5
