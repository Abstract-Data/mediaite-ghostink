"""Process-local keyed caches for heavy ML model handles (not thread-safe)."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")


class KeyedModelCache:
    """Load-once cache keyed by a hashable (model id, device tuple, etc.)."""

    __slots__ = ("_data",)

    def __init__(self) -> None:
        self._data: dict[Hashable, Any] = {}

    def get_or_load(self, key: Hashable, factory: Callable[[], T]) -> T:
        if key not in self._data:
            self._data[key] = factory()
        return self._data[key]

    def clear(self) -> None:
        self._data.clear()
