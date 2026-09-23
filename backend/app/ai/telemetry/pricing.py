"""
Cost calculation and model pricing telemetry.
Never guesses pricing for unknown models; strictly returns None if pricing is unconfigured.
"""

from __future__ import annotations

from typing import Any

# Default well-known official model pricing tables (USD per 1,000,000 tokens)
# Only standard recognized baseline models are registered here.
DEFAULT_MODEL_PRICING: dict[str, dict[str, Any]] = {
    "gpt-4o-mini": {
        "input_price_per_1m": 0.15,
        "output_price_per_1m": 0.60,
        "cached_input_price_per_1m": 0.075,
        "currency": "USD",
    },
    "gpt-4o": {
        "input_price_per_1m": 2.50,
        "output_price_per_1m": 10.00,
        "cached_input_price_per_1m": 1.25,
        "currency": "USD",
    },
}


def _normalize_model_alias(m: str) -> str:
    norm = m.strip().lower()
    if norm.startswith("gpt-4o-mini-"):
        return "gpt-4o-mini"
    if norm.startswith("gpt-4o-") and not norm.startswith("gpt-4o-mini"):
        return "gpt-4o"
    return norm


def calculate_cost(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_input_tokens: int | None = None,
    custom_pricing: dict[str, dict[str, Any]] | None = None,
    provider: str | None = None,
    **kwargs: Any,
) -> tuple[float | None, str | None]:
    """
    Calculate cost for token consumption.

    Returns (cost_in_currency, currency) or (None, None) if model pricing is not configured.
    """
    if not model or input_tokens is None or output_tokens is None:
        return None, None

    pricing_map = {**DEFAULT_MODEL_PRICING, **(custom_pricing or {})}
    prices = pricing_map.get(model) or pricing_map.get(_normalize_model_alias(model))
    if not prices:
        # Unknown/Custom model with no configured pricing -> NEVER guess
        return None, None

    in_price = float(prices.get("input_price_per_1m", 0.0))
    out_price = float(prices.get("output_price_per_1m", 0.0))
    cached_price = float(prices.get("cached_input_price_per_1m", in_price * 0.5))
    currency = str(prices.get("currency", "USD"))

    cached_cnt = cached_input_tokens or 0
    regular_in_cnt = max(0, input_tokens - cached_cnt)

    total_cost = (
        (regular_in_cnt * in_price / 1_000_000.0)
        + (cached_cnt * cached_price / 1_000_000.0)
        + (output_tokens * out_price / 1_000_000.0)
    )
    return round(total_cost, 6), currency
