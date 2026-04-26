"""Deterministic variable sampling + prompt rendering (spec §8).

Mirrors the TS spec in §8.1 closely (same control flow + the Math.floor
clamping pattern) but uses Python's Mersenne Twister for the RNG. Output
is reproducible per (seed, variable_schema) Python-side; we never compare
sampled values against a JS implementation, so cross-language drift is
not a concern for v1."""

from __future__ import annotations

import math
import string
from random import Random
from typing import Any

from jinja2 import Environment, StrictUndefined

# Templates run with StrictUndefined so an unfilled variable raises rather
# than rendering a confusing empty string. Render in autoescape=False since
# the candidate page already escapes via React.
_jinja_env = Environment(
    autoescape=False,
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


def _sample_int(rng: Random, spec: dict[str, Any]) -> int:
    min_v = int(spec["min"])
    max_v = int(spec["max"])
    step = int(spec.get("step", 1)) or 1
    steps = (max_v - min_v) // step + 1
    return math.floor(rng.random() * steps) * step + min_v


def _sample_float(rng: Random, spec: dict[str, Any]) -> float:
    min_v = float(spec["min"])
    max_v = float(spec["max"])
    decimals = int(spec.get("decimals", 2))
    return round(rng.random() * (max_v - min_v) + min_v, decimals)


def _pick(rng: Random, items: list[Any]) -> Any:
    if not items:
        raise ValueError("choice/dataset variable has no options.")
    return items[math.floor(rng.random() * len(items))]


def _render_pattern(rng: Random, pattern: str) -> str:
    """Lightweight string_template substitution.

    Handles two tokens:
      {alpha:N}  → N random uppercase letters
      {digit:N}  → N random digits

    Anything else is passed through verbatim. Useful for synthetic order
    IDs ("ORD-{alpha:3}-{digit:4}") without pulling in a full templating
    grammar."""

    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "{":
            close = pattern.find("}", i + 1)
            if close == -1:
                out.append(pattern[i:])
                break
            body = pattern[i + 1 : close]
            if ":" in body:
                kind, _, count_str = body.partition(":")
                try:
                    count = int(count_str)
                except ValueError:
                    out.append(pattern[i : close + 1])
                    i = close + 1
                    continue
                if kind == "alpha":
                    out.append(
                        "".join(_pick(rng, list(string.ascii_uppercase)) for _ in range(count))
                    )
                elif kind == "digit":
                    out.append(
                        "".join(_pick(rng, list(string.digits)) for _ in range(count))
                    )
                else:
                    out.append(pattern[i : close + 1])
                i = close + 1
                continue
            out.append(pattern[i : close + 1])
            i = close + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def sample_variables(
    schema: dict[str, dict[str, Any]],
    seed: int | str,
) -> dict[str, Any]:
    """Sample concrete values for every entry in `schema` (spec §8.1)."""

    rng = Random(seed)
    result: dict[str, Any] = {}
    for name, spec in schema.items():
        kind = spec.get("kind")
        if kind == "int":
            result[name] = _sample_int(rng, spec)
        elif kind == "float":
            result[name] = _sample_float(rng, spec)
        elif kind == "choice":
            result[name] = _pick(rng, list(spec["options"]))
        elif kind == "dataset":
            result[name] = _pick(rng, list(spec["pool"]))
        elif kind == "string_template":
            result[name] = _render_pattern(rng, str(spec["pattern"]))
        else:
            raise ValueError(f"Unsupported variable kind: {kind!r}")
    return result


def render_prompt(template: str, variables: dict[str, Any]) -> str:
    """Render a Jinja-flavored prompt template (spec §8.2)."""

    return _jinja_env.from_string(template).render(**variables)


def question_seed(random_seed: int, question_id: str) -> str:
    """Stable per-question seed so reordering questions does not reshuffle
    earlier variables."""
    return f"{random_seed}::{question_id}"
