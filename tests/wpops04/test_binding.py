"""WP-OPS-04 acceptance ④⑥ — services bind locally by default; a non-local bind
requires explicit confirmation.
"""

from __future__ import annotations

import pytest

from ops.hubguard.binding import (
    DEFAULT_BIND_HOST,
    NonLocalBindingError,
    is_local,
    resolve_bind_host,
)

_ALL_INTERFACES = "0.0.0.0"


# --- Acceptance ④ : the default service binding is a local address.


def test_default_binding_is_local() -> None:
    resolved = resolve_bind_host(requested=None)
    assert resolved == DEFAULT_BIND_HOST
    assert is_local(resolved)


def test_explicit_loopback_is_accepted_without_confirmation() -> None:
    assert resolve_bind_host(requested="127.0.0.1") == "127.0.0.1"
    assert resolve_bind_host(requested="localhost") == "localhost"


# --- Acceptance ⑥ : a non-local bind is refused unless explicitly confirmed.


def test_non_local_binding_requires_confirmation() -> None:
    with pytest.raises(NonLocalBindingError) as excinfo:
        resolve_bind_host(requested=_ALL_INTERFACES, confirmed=False)
    assert excinfo.value.host == _ALL_INTERFACES


def test_non_local_binding_allowed_once_confirmed() -> None:
    assert resolve_bind_host(requested=_ALL_INTERFACES, confirmed=True) == _ALL_INTERFACES


def test_all_interfaces_is_not_classified_local() -> None:
    # Guards against a well-meaning widening of LOCAL_HOSTS that would make the
    # confirmation gate vacuous.
    assert not is_local(_ALL_INTERFACES)
