"""Load the frozen OA-* registry and expose each code as a referenceable symbol.

The registry is canon and every emission point is a consumer (14 §2.10): a code
string must arrive at an emission call as a *symbol* read from here, never as an
inline literal. So this module both loads `error_registry.yaml` and publishes the
`codes` namespace whose attributes (`codes.OA_CAN_003`) are the only sanctioned
way to name a code in product code — the static check forbids the literal form.

Ownership: this module reads the frozen file and never writes it. The file is the
authority; if the two disagree, the file wins and a checker reports the drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from contracts.errors.constants import (
    CODE_PATTERN,
    CONTRACT_ID,
    DOMAINS,
    REGISTRY_PATH,
    REQUIRED_FIELDS,
)


class UnregisteredCodeError(KeyError):
    """Raised when code that is not in the frozen registry is asked for.

    This is the runtime half of the unregistered-code ban (acceptance ⑦): the
    static check catches literals before merge, and this catches a computed or
    stale string at emission time.
    """


@dataclass(frozen=True)
class ErrorCode:
    """One registered code with its ten contract fields plus provenance.

    Attributes mirror the frozen row exactly. `hardware_id`, `first_seen_t` and
    `count` are runtime-populated, so they are `None`/`0` on a definition read;
    `source` records which document authored the row (14 §2.10 vs 01 §4.5).
    """

    code: str
    severity: int
    message_ko: str
    message_en: str
    hardware_id: str | None
    subsystem: str
    recovery_hint: str
    doc_url: str
    first_seen_t: int | None
    count: int
    source: str

    @property
    def domain(self) -> str:
        """Return the `OA-<domain>` prefix of this code.

        Returns:
            (str) The domain prefix, e.g. `OA-CAN`.
        """
        match = CODE_PATTERN.match(self.code)
        if match is None:
            return ""
        return f"OA-{match.group('domain')}"


class Registry:
    """The loaded CTR-ERR@v1 registry: codes, domains, severities, nibble map.

    A `Registry` is immutable after construction. Consumers ask it for a code by
    symbol; asking for an unregistered code raises `UnregisteredCodeError` rather
    than returning a fabricated row.
    """

    def __init__(self, document: dict[str, Any]) -> None:
        """Build a registry from a parsed `error_registry.yaml` document.

        Args:
            document: The YAML mapping loaded from the frozen file.
        """
        self.contract = str(document.get("contract", ""))
        self.severity_levels = dict(document.get("severity_levels", {}) or {})
        self.domains = tuple(document.get("domains", []) or [])
        self.raw_codes = list(document.get("codes", []) or [])
        self.nibble_map = list(document.get("damiao_err_nibble_map", []) or [])
        self.fields = tuple(document.get("fields", []) or [])
        self.codes = self._index_codes(self.raw_codes)

    @staticmethod
    def _index_codes(rows: list[dict[str, Any]]) -> dict[str, ErrorCode]:
        """Index rows by code, keeping only rows with the full field set.

        A partial row is skipped here rather than half-built, so that a consumer
        never receives an `ErrorCode` missing a contract field; the field-coverage
        checker reports the partial row separately.

        Args:
            rows: Raw code mappings from the file.

        Returns:
            (dict[str, ErrorCode]) Complete rows keyed by code string.
        """
        indexed: dict[str, ErrorCode] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            if any(field not in row for field in REQUIRED_FIELDS):
                continue
            code = str(row["code"])
            indexed[code] = ErrorCode(
                code=code,
                severity=row["severity"],
                message_ko=str(row["message_ko"]),
                message_en=str(row["message_en"]),
                hardware_id=row["hardware_id"],
                subsystem=str(row["subsystem"]),
                recovery_hint=str(row["recovery_hint"]),
                doc_url=str(row["doc_url"]),
                first_seen_t=row["first_seen_t"],
                count=int(row.get("count", 0) or 0),
                source=str(row.get("source", "")),
            )
        return indexed

    def __contains__(self, code: object) -> bool:
        """Report whether a code string is registered.

        Args:
            code: Candidate code string.

        Returns:
            (bool) True when the code has a complete registered row.
        """
        return isinstance(code, str) and code in self.codes

    def get(self, code: str) -> ErrorCode:
        """Return the registered code, or raise if it is unknown.

        Args:
            code: The code string, normally read from a `codes` symbol.

        Returns:
            (ErrorCode) The registered row.

        Raises:
            UnregisteredCodeError: When the code is not in the frozen registry.
        """
        try:
            return self.codes[code]
        except KeyError as missing:
            raise UnregisteredCodeError(code) from missing


class _CodeSymbols:
    """Attribute access to registered code strings (`codes.OA_CAN_003`).

    This exists so product code names a code by symbol, not by literal. An unknown
    attribute raises `AttributeError`, so a typo fails at import/first-use rather
    than shipping a string no registry row backs.
    """

    def __init__(self, registry: Registry) -> None:
        """Bind the namespace to a registry.

        Args:
            registry: The registry whose codes become attributes.
        """
        self._by_symbol = {code.replace("-", "_"): code for code in registry.codes}

    def __getattr__(self, name: str) -> str:
        """Return the code string for a symbol like `OA_CAN_003`.

        Args:
            name: The Python-identifier form of a code.

        Returns:
            (str) The code string.

        Raises:
            AttributeError: When no registered code maps to the symbol.
        """
        try:
            return self._by_symbol[name]
        except KeyError as missing:
            raise AttributeError(name) from missing

    def __dir__(self) -> list[str]:
        """List the available code symbols for tooling and `dir()`.

        Returns:
            (list[str]) Symbol names, sorted.
        """
        return sorted(self._by_symbol)


def load_registry() -> Registry:
    """Load the frozen registry from its committed path.

    Returns:
        (Registry) The parsed CTR-ERR@v1 registry.
    """
    document = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return Registry(document if isinstance(document, dict) else {})


REGISTRY = load_registry()
codes = _CodeSymbols(REGISTRY)

__all__ = [
    "CONTRACT_ID",
    "DOMAINS",
    "REGISTRY",
    "ErrorCode",
    "Registry",
    "UnregisteredCodeError",
    "codes",
    "load_registry",
]
