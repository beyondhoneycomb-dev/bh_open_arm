"""The sanctioned emission path: a code must be registered to be raised or logged.

14 §2.10 makes the registry canon and every emission a consumer. So the only way
to emit a code is through here, with a code that resolves in the frozen registry;
an unregistered string is rejected at runtime (acceptance ⑦), the runtime twin of
the static inline-literal ban. Callers pass a symbol from `contracts.errors.codes`,
never a bare string literal.
"""

from __future__ import annotations

from typing import Any

from contracts.errors.registry import REGISTRY, ErrorCode, Registry, UnregisteredCodeError


class OaError(Exception):
    """An error carrying a registered OA-* code and its resolved row.

    The message is the registry's English text, so two raises of the same code
    never drift into two human descriptions of one failure.
    """

    def __init__(self, code: str, registry: Registry = REGISTRY) -> None:
        """Build the error, resolving the code against the registry.

        Args:
            code: The code string, from a `codes` symbol.
            registry: The registry to resolve against; defaults to the frozen one.

        Raises:
            UnregisteredCodeError: When the code is not registered.
        """
        self.entry: ErrorCode = registry.get(code)
        self.code = self.entry.code
        super().__init__(f"{self.entry.code}: {self.entry.message_en}")


def make_error(code: str, registry: Registry = REGISTRY) -> OaError:
    """Build an `OaError` for a registered code.

    Args:
        code: The code string, from a `codes` symbol.
        registry: The registry to resolve against.

    Returns:
        (OaError) The constructed error.

    Raises:
        UnregisteredCodeError: When the code is not registered.
    """
    return OaError(code, registry)


def emit(sink: Any, code: str, registry: Registry = REGISTRY, **fields: Any) -> dict[str, Any]:
    """Resolve a code and hand a structured event to a sink.

    The event shape matches the WP-OPS-05 structured logger (subsystem + event +
    fields), so a code emission and a diagnostic land in the same record stream.

    Args:
        sink: A callable receiving the built event dict, e.g. a logger emit.
        code: The code string, from a `codes` symbol.
        registry: The registry to resolve against.
        **fields: Extra payload merged into the event.

    Returns:
        (dict[str, Any]) The event dict handed to the sink.

    Raises:
        UnregisteredCodeError: When the code is not registered.
    """
    entry = registry.get(code)
    event = {
        "code": entry.code,
        "severity": entry.severity,
        "subsystem": entry.subsystem,
        "message_en": entry.message_en,
        "message_ko": entry.message_ko,
        **fields,
    }
    sink(event)
    return event


__all__ = ["OaError", "UnregisteredCodeError", "emit", "make_error"]
