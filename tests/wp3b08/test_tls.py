"""Acceptance ④: HTTPS/WSS:8443 with configurable TLS certificate/key paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.teleop.webxr.constants import DEFAULT_TLS_HOST, DEFAULT_TLS_PORT
from backend.teleop.webxr.tls import TlsConfig, TlsConfigError, tls_config


def test_default_port_is_8443(tmp_path: Path) -> None:
    config = tls_config(tmp_path / "cert.pem", tmp_path / "key.pem")
    assert config.port == 8443
    assert DEFAULT_TLS_PORT == 8443
    assert config.host == DEFAULT_TLS_HOST


def test_certificate_and_key_paths_are_configurable(tmp_path: Path) -> None:
    cert = tmp_path / "sub" / "server.crt"
    key = tmp_path / "sub" / "server.key"
    config = tls_config(cert, key, host="127.0.0.1", port=9443)
    assert config.certificate_path == cert
    assert config.key_path == key
    assert config.host == "127.0.0.1"
    assert config.port == 9443


def test_missing_certificate_path_is_rejected() -> None:
    # WebXR forces HTTPS, so a session with no certificate cannot be served at all. A
    # path that names no file (root) stands in for "no certificate file configured".
    with pytest.raises(TlsConfigError):
        TlsConfig(certificate_path=Path("/"), key_path=Path("key.pem"), host="0.0.0.0", port=8443)


def test_missing_key_path_is_rejected() -> None:
    with pytest.raises(TlsConfigError):
        TlsConfig(certificate_path=Path("cert.pem"), key_path=Path("/"), host="0.0.0.0", port=8443)


def test_port_out_of_range_is_rejected(tmp_path: Path) -> None:
    for bad_port in (0, -1, 70000):
        with pytest.raises(TlsConfigError):
            tls_config(tmp_path / "cert.pem", tmp_path / "key.pem", port=bad_port)


def test_material_present_reflects_disk(tmp_path: Path) -> None:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    config = tls_config(cert, key)
    assert config.material_present() is False  # paths fixed, files not yet written
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    assert config.material_present() is True
