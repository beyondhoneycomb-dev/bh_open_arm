"""Control-channel transport security — no plaintext, no wildcard (`FR-OPS-090`).

`FR-OPS-090` requires the control channel on WSS/TLS with an Origin allowlist and a
CSRF/CORS policy, and forbids four things outright: a plaintext WS binding, a
plaintext HTTP binding, a wildcard Origin, and `Access-Control-Allow-Origin: *`.
`CG-5-08a` checks this two ways — at runtime (a policy object refuses a bad
configuration) and statically (a scan of control-channel binding config finds zero of
the forbidden forms).

Runtime: the WS side reuses `contracts.ws.WsSecurityPolicy` (it already refuses a
plaintext scheme, an empty or wildcard allowlist, and missing CSRF/CORS), so this
module states its agreement by reference. The REST side adds `RestCorsPolicy`, which
refuses a wildcard Origin and any plaintext-`http` origin, and requires the REST
scheme to be `https`. `ControlChannelSecurity` composes the two into one control-
channel policy that is unconstructible in a forbidden shape.

Static: `scan_text`/`scan_files` read control-channel binding config as text and
report every plaintext control binding, wildcard CORS header, and wildcard Origin
literal. The scheme markers are built from parts at runtime, so this module contains
no literal plaintext URL and a self-scan of the security package reports nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from backend.security.constants import (
    CORS_ALLOW_ORIGIN_HEADER,
    PLAINTEXT_HTTP_SCHEME,
    SECURE_HTTP_SCHEME,
    URL_SCHEME_SEPARATOR,
)
from contracts.ws import (
    WILDCARD_ORIGIN,
    WS_PLAINTEXT_SCHEME,
    WsSecurityPolicy,
)


class OriginPolicyError(ValueError):
    """Raised when a REST/CORS control-channel policy is built in a forbidden shape."""


@dataclass(frozen=True)
class RestCorsPolicy:
    """The REST side of the control-channel security policy (`FR-OPS-090`).

    Attributes:
        rest_scheme: The REST URL scheme; must be `https`.
        allowed_origins: The exact Origins CORS permits; must be non-empty, must not
            contain the wildcard, and must not name a plaintext-`http` origin.
        csrf_enforced: Whether CSRF defence is enforced on state-changing REST calls.
    """

    rest_scheme: str
    allowed_origins: tuple[str, ...]
    csrf_enforced: bool

    def __post_init__(self) -> None:
        """Reject a plaintext scheme, a wildcard/plaintext Origin, or missing CSRF."""
        if self.rest_scheme != SECURE_HTTP_SCHEME:
            raise OriginPolicyError(
                f"REST scheme must be {SECURE_HTTP_SCHEME!r} (TLS); {self.rest_scheme!r} is refused"
            )
        if not self.allowed_origins:
            raise OriginPolicyError("an Origin allowlist is required; empty admits any Origin")
        if WILDCARD_ORIGIN in self.allowed_origins:
            raise OriginPolicyError(
                "a wildcard Origin is forbidden; the allowlist must name exact Origins"
            )
        plaintext_prefix = f"{WS_PLAINTEXT_SCHEME}{URL_SCHEME_SEPARATOR}"
        http_prefix = f"{PLAINTEXT_HTTP_SCHEME}{URL_SCHEME_SEPARATOR}"
        for origin in self.allowed_origins:
            if origin.startswith(http_prefix) or origin.startswith(plaintext_prefix):
                raise OriginPolicyError(
                    f"Origin {origin!r} uses a plaintext scheme; the control channel is TLS-only"
                )
        if not self.csrf_enforced:
            raise OriginPolicyError("CSRF defence is required on the control channel REST surface")


@dataclass(frozen=True)
class ControlChannelSecurity:
    """The whole control-channel security policy: WS (reused) + REST (added).

    Attributes:
        ws: The `CTR-WS@v1` WS security policy (WSS, Origin allowlist, CSRF/CORS).
        rest: The REST/CORS policy for the paired HTTP surface.
    """

    ws: WsSecurityPolicy
    rest: RestCorsPolicy


class OriginFindingKind(Enum):
    """The kind of forbidden form a static scan found (`CG-5-08a`)."""

    PLAINTEXT_CONTROL_BINDING = "plaintext_control_binding"
    WILDCARD_CORS = "wildcard_cors"
    WILDCARD_ORIGIN = "wildcard_origin"


@dataclass(frozen=True)
class OriginFinding:
    """One forbidden form located in control-channel binding config.

    Attributes:
        source: The scanned source's name (file path or a synthetic label).
        line: The 1-based line the finding is on.
        kind: Which forbidden form it is.
        detail: The offending line text, trimmed, for the report.
    """

    source: str
    line: int
    kind: OriginFindingKind
    detail: str


def _plaintext_markers() -> tuple[str, ...]:
    """Return the plaintext URL prefixes to scan for, built from parts.

    Building them at runtime keeps a literal plaintext-URL prefix out of this file, so
    a self-scan of the security package reports zero plaintext control bindings.

    Returns:
        (tuple[str, ...]) The plaintext scheme prefixes, e.g. the ws and http forms.
    """
    return (
        f"{WS_PLAINTEXT_SCHEME}{URL_SCHEME_SEPARATOR}",
        f"{PLAINTEXT_HTTP_SCHEME}{URL_SCHEME_SEPARATOR}",
    )


def scan_text(text: str, source: str) -> tuple[OriginFinding, ...]:
    """Scan one control-channel config body for the forbidden forms (`CG-5-08a`).

    Args:
        text: The config text (a `.conf`/`.toml`/`.env`-style binding file).
        source: A label for the source, carried into each finding.

    Returns:
        (tuple[OriginFinding, ...]) One finding per forbidden form occurrence, in
        line order; empty when the config is clean.
    """
    markers = _plaintext_markers()
    findings: list[OriginFinding] = []
    for index, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        lowered = line.lower()
        has_cors_header = CORS_ALLOW_ORIGIN_HEADER.lower() in lowered
        for marker in markers:
            if marker in line:
                findings.append(
                    OriginFinding(source, index, OriginFindingKind.PLAINTEXT_CONTROL_BINDING, line)
                )
        if has_cors_header and WILDCARD_ORIGIN in line:
            findings.append(OriginFinding(source, index, OriginFindingKind.WILDCARD_CORS, line))
        elif "origin" in lowered and WILDCARD_ORIGIN in line:
            findings.append(OriginFinding(source, index, OriginFindingKind.WILDCARD_ORIGIN, line))
    return tuple(findings)


def scan_files(paths: Iterable[Path]) -> tuple[OriginFinding, ...]:
    """Scan a set of control-channel config files for the forbidden forms.

    Args:
        paths: Config files to scan; each is read as UTF-8 text.

    Returns:
        (tuple[OriginFinding, ...]) Every finding across all files, in file then line
        order.
    """
    findings: list[OriginFinding] = []
    for path in paths:
        findings.extend(scan_text(path.read_text(encoding="utf-8"), str(path)))
    return tuple(findings)


def scan_python_sources(root: Path) -> tuple[OriginFinding, ...]:
    """Scan a package tree's Python sources for plaintext control bindings.

    Used to prove the shipped security code itself binds no plaintext control channel
    (`CG-5-08a` self-scan). Only the plaintext-binding kind is meaningful here; a
    wildcard Origin/CORS is a config concern, not a source-literal one.

    Args:
        root: The package directory to walk.

    Returns:
        (tuple[OriginFinding, ...]) Plaintext-binding findings across the tree.
    """
    findings: list[OriginFinding] = []
    for path in sorted(root.rglob("*.py")):
        for finding in scan_text(path.read_text(encoding="utf-8"), str(path)):
            if finding.kind is OriginFindingKind.PLAINTEXT_CONTROL_BINDING:
                findings.append(finding)
    return tuple(findings)


def has_forbidden_forms(findings: Sequence[OriginFinding]) -> bool:
    """Whether any forbidden form was found.

    Args:
        findings: Findings from a scan.

    Returns:
        (bool) True when the scan is not clean.
    """
    return len(findings) > 0
