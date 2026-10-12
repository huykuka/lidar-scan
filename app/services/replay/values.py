"""Helpers for comparing/writing node config values.

The UI stores numeric parameters as strings (``'0.7'``) while overrides arrive as numbers,
so equality and writing must be tolerant of that.
"""
from __future__ import annotations

import math
from typing import Any


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def same_value(a: Any, b: Any) -> bool:
    """Equality that treats ``'0.7'`` and ``0.7`` as the same, and lists element-wise."""
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) != isinstance(b, bool):
        return False  # Python says True == 1; for a config parameter they are different values
    na, nb = _as_number(a), _as_number(b)
    if na is not None and nb is not None:
        return math.isclose(na, nb, rel_tol=1e-9, abs_tol=1e-12)
    return a == b


def value_for_config(existing: Any, new: Any) -> Any:
    """Value to store so the saved config keeps its existing style (number-as-string)."""
    if isinstance(existing, str) and _as_number(existing) is not None and _as_number(new) is not None \
            and not isinstance(new, bool):
        return str(new)
    return new
