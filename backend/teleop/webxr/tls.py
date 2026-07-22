"""TLS transport configuration for the WebXR path (WP-3B-08, acceptance ④).

WebXR forces a secure context: `navigator.xr.requestSession('immersive-ar')` is
only reachable from an HTTPS origin, so this path has no plaintext mode to fall
back to (`05` §2.7 path B, `FR-TEL-015`). A certificate and a private-key path are
therefore not optional configuration — a session that cannot present a certificate
cannot be served at all, so this module rejects a config missing either, rather than
letting a headset hit a dead port at connect time.

The port default is 8443 (`05` §2.7 config table). This module does not open a
socket or read the key material — that is the live session, which needs a headset
browser and is deferred (`backend.teleop.webxr.reverify`). It fixes and validates
the paths so the deferred bring-up has one definition of where the material lives.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.teleop.webxr.constants import DEFAULT_TLS_HOST, DEFAULT_TLS_PORT

# The smallest and largest a TCP port may be. A port outside this is a config typo,
# not a bindable endpoint, so the config rejects it before the deferred bring-up
# tries to listen.
MIN_TCP_PORT = 1
MAX_TCP_PORT = 65535


class TlsConfigError(ValueError):
    """Raised when a WebXR TLS config is missing material HTTPS makes mandatory."""


@dataclass(frozen=True)
class TlsConfig:
    """The HTTPS/WSS endpoint the WebXR path is served on.

    Attributes:
        certificate_path: Path to the TLS certificate (`--tls-certificate-file`).
        key_path: Path to the TLS private key (`--tls-key-file`).
        host: Interface to bind; defaults to all interfaces.
        port: TCP port; defaults to the WebXR spec default 8443.
    """

    certificate_path: Path
    key_path: Path
    host: str
    port: int

    def __post_init__(self) -> None:
        """Reject a config that could not serve a WebXR session.

        Raises:
            TlsConfigError: If either the certificate or the key path names no file
                (WebXR cannot be served without both), or the port is out of range.
        """
        # `.name` is empty for an empty path (`Path("")` normalises to `.`) and for a
        # bare directory, so it is the honest "a certificate FILE was named" check.
        if not self.certificate_path.name:
            raise TlsConfigError("WebXR requires a TLS certificate file path; HTTPS is mandatory")
        if not self.key_path.name:
            raise TlsConfigError("WebXR requires a TLS private-key file path; HTTPS is mandatory")
        if not MIN_TCP_PORT <= self.port <= MAX_TCP_PORT:
            raise TlsConfigError(
                f"TLS port {self.port} is outside the TCP range [{MIN_TCP_PORT}, {MAX_TCP_PORT}]"
            )

    def material_present(self) -> bool:
        """Report whether both the certificate and key files exist on disk.

        The live session needs both files readable; the offline config only fixes
        their paths, so this is a bring-up preflight, not a construction invariant.

        Returns:
            (bool) True when both paths point at existing files.
        """
        return self.certificate_path.is_file() and self.key_path.is_file()


def tls_config(
    certificate_path: Path,
    key_path: Path,
    host: str = DEFAULT_TLS_HOST,
    port: int = DEFAULT_TLS_PORT,
) -> TlsConfig:
    """Build a validated WebXR TLS config, defaulting host and port to the spec.

    Args:
        certificate_path: Path to the TLS certificate.
        key_path: Path to the TLS private key.
        host: Interface to bind; defaults to all interfaces.
        port: TCP port; defaults to 8443.

    Returns:
        (TlsConfig) The validated endpoint config.

    Raises:
        TlsConfigError: If the certificate/key path is empty or the port is invalid.
    """
    return TlsConfig(certificate_path=certificate_path, key_path=key_path, host=host, port=port)
