"""CG-5-08a — no plaintext control binding, no wildcard Origin/CORS (FR-OPS-090).

Two ways, as the gate requires. Runtime: the control-channel policy object refuses a
plaintext scheme, a wildcard Origin, a plaintext Origin, and missing CSRF. Static: a
scan of control-channel binding config finds every forbidden form in a bad config and
zero in a good one, and the shipped security package binds no plaintext channel.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend import security
from backend.security.origin_policy import (
    ControlChannelSecurity,
    OriginFindingKind,
    OriginPolicyError,
    RestCorsPolicy,
    has_forbidden_forms,
    scan_python_sources,
    scan_text,
)
from contracts.ws import WsError, WsSecurityPolicy

_GOOD_ORIGIN = "https://console.openarm.local"

_BAD_CONFIG = """
[control_channel]
ws_bind = ws://0.0.0.0:8080
rest_bind = http://0.0.0.0:8000
Access-Control-Allow-Origin: *
origin_allowlist = ["*"]
"""

_GOOD_CONFIG = """
[control_channel]
ws_bind = wss://0.0.0.0:8443
rest_bind = https://0.0.0.0:8000
Access-Control-Allow-Origin: https://console.openarm.local
origin_allowlist = ["https://console.openarm.local"]
"""


def _good_ws() -> WsSecurityPolicy:
    return WsSecurityPolicy(scheme="wss", origin_allowlist=(_GOOD_ORIGIN,), csrf_cors_enforced=True)


def _good_rest() -> RestCorsPolicy:
    return RestCorsPolicy(rest_scheme="https", allowed_origins=(_GOOD_ORIGIN,), csrf_enforced=True)


def test_valid_control_channel_policy_constructs() -> None:
    policy = ControlChannelSecurity(ws=_good_ws(), rest=_good_rest())
    assert policy.ws.scheme == "wss"
    assert policy.rest.rest_scheme == "https"


def test_plaintext_ws_scheme_is_refused() -> None:
    with pytest.raises(WsError):
        WsSecurityPolicy(scheme="ws", origin_allowlist=(_GOOD_ORIGIN,), csrf_cors_enforced=True)


def test_wildcard_ws_origin_is_refused() -> None:
    with pytest.raises(WsError):
        WsSecurityPolicy(scheme="wss", origin_allowlist=("*",), csrf_cors_enforced=True)


def test_plaintext_rest_scheme_is_refused() -> None:
    with pytest.raises(OriginPolicyError):
        RestCorsPolicy(rest_scheme="http", allowed_origins=(_GOOD_ORIGIN,), csrf_enforced=True)


def test_wildcard_rest_origin_is_refused() -> None:
    with pytest.raises(OriginPolicyError):
        RestCorsPolicy(rest_scheme="https", allowed_origins=("*",), csrf_enforced=True)


def test_plaintext_rest_origin_is_refused() -> None:
    with pytest.raises(OriginPolicyError):
        RestCorsPolicy(
            rest_scheme="https",
            allowed_origins=("http://console.openarm.local",),
            csrf_enforced=True,
        )


def test_missing_csrf_is_refused() -> None:
    with pytest.raises(OriginPolicyError):
        RestCorsPolicy(rest_scheme="https", allowed_origins=(_GOOD_ORIGIN,), csrf_enforced=False)


def test_static_scan_finds_every_forbidden_form_in_bad_config() -> None:
    findings = scan_text(_BAD_CONFIG, "bad_config")
    kinds = {finding.kind for finding in findings}

    assert OriginFindingKind.PLAINTEXT_CONTROL_BINDING in kinds
    assert OriginFindingKind.WILDCARD_CORS in kinds
    assert OriginFindingKind.WILDCARD_ORIGIN in kinds
    # Both the ws and http plaintext bindings are caught.
    plaintext = [f for f in findings if f.kind is OriginFindingKind.PLAINTEXT_CONTROL_BINDING]
    assert len(plaintext) == 2
    assert has_forbidden_forms(findings)


def test_static_scan_passes_a_good_config() -> None:
    findings = scan_text(_GOOD_CONFIG, "good_config")
    assert findings == ()
    assert not has_forbidden_forms(findings)


def test_static_scan_over_config_files(tmp_path: Path) -> None:
    bad = tmp_path / "control_bad.conf"
    good = tmp_path / "control_good.conf"
    bad.write_text(_BAD_CONFIG, encoding="utf-8")
    good.write_text(_GOOD_CONFIG, encoding="utf-8")

    from backend.security.origin_policy import scan_files

    assert has_forbidden_forms(scan_files([bad]))
    assert scan_files([good]) == ()


def test_shipped_security_package_binds_no_plaintext_control_channel() -> None:
    root = Path(security.__file__).resolve().parent
    assert scan_python_sources(root) == ()
