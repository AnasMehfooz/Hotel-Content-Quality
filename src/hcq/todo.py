"""Marks the functions that are yours to implement.

A ``@todo`` function raises ``NotImplementedError`` with a pointer to its milestone. Delete the
decorator when you implement the function; ``hcq progress`` and the acceptance tests pick that up.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def todo(milestone: str, hint: str = "") -> Callable[[F], F]:
    def decorate(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError(f"{milestone}: implement {fn.__qualname__}. {hint}".strip())

        wrapper.__hcq_todo__ = milestone  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorate


def is_todo(fn: Callable[..., Any]) -> bool:
    return bool(getattr(fn, "__hcq_todo__", None))
