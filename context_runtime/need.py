from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator, Protocol, runtime_checkable


class NeedUnavailable(LookupError):
    """Raised when no current agent information need is available."""


@runtime_checkable
class NeedProvider(Protocol):
    """Adapter boundary for supplying the current agent information need."""

    def current_need(self) -> str | None:
        ...


class ContextVarNeedProvider:
    """Default async-safe provider for framework adapters and scoped calls."""

    def __init__(self) -> None:
        self._current: ContextVar[str | None] = ContextVar(
            "context_runtime_current_need", default=None
        )

    def current_need(self) -> str | None:
        return self._current.get()

    @contextmanager
    def scope(self, need: str) -> Generator[str, None, None]:
        normalized = _normalize_need(need)
        token = self._current.set(normalized)
        try:
            yield normalized
        finally:
            self._current.reset(token)


def resolve_need(explicit: str | None, provider: NeedProvider) -> str:
    if explicit is not None:
        return _normalize_need(explicit)
    provided = provider.current_need()
    if provided is None:
        raise NeedUnavailable(
            "No agent need is available. Pass need= explicitly or configure a NeedProvider."
        )
    return _normalize_need(provided)


def _normalize_need(need: str) -> str:
    normalized = need.strip()
    if not normalized:
        raise NeedUnavailable("Agent need cannot be empty")
    return normalized
