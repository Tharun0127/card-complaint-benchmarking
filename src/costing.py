"""Token and cost arithmetic for the classifier. Pure functions, covered by tests.

Prices are USD per million tokens at paid-tier list price: Anthropic as of 25 Sep 2026,
Google Gemini as of 30 Sep 2026. The two providers bill differently:
  - Anthropic requests go through the Message Batches API at half price, and writing the
    shared instructions to a 1-hour cache costs 2x the input price.
  - Gemini requests are ordinary (not batch) calls at full price. Caching is implicit:
    a cache hit is discounted and a miss is billed as plain input, with no write fee.
"""
from __future__ import annotations

from dataclasses import dataclass

BATCH_DISCOUNT = 0.5
DEFAULT_BUDGET_USD = 10.0


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float
    cache_read: float
    min_cacheable_tokens: int
    thinks: bool  # thinking tokens are billed as output
    provider: str = "anthropic"
    cache_write_multiplier: float = 2.0  # cost of a cache miss relative to plain input
    batch: bool = True  # requests are sent through a half-price batch API


PRICES: dict[str, ModelPrice] = {
    "claude-opus-5-5": ModelPrice(4.00, 20.00, 0.20, 512, True),
    "claude-sonnet-5-5": ModelPrice(2.00, 10.00, 0.20, 512, True),
    "claude-haiku-4-5": ModelPrice(1.00, 5.00, 0.10, 4096, False),
    "gemini-3.8-flash": ModelPrice(0.75, 3.75, 0.075, 1024, True, "gemini", 1.0, False),
    "gemini-3.6-flash": ModelPrice(0.75, 3.75, 0.075, 1024, True, "gemini", 1.0, False),
    "gemini-3.5-flash-lite": ModelPrice(0.30, 2.50, 0.03, 1024, True, "gemini", 1.0, False),
}


def usage_cost(
    model: str,
    input_tokens: float,
    output_tokens: float,
    cache_read_tokens: float = 0,
    cache_write_tokens: float = 0,
    batch: bool = True,
) -> float:
    """Cost in USD of one or more requests given their token usage.

    `input_tokens` is the uncached input only. Output includes thinking tokens.
    """
    p = PRICES[model]
    cost = (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_read_tokens * p.cache_read
        + cache_write_tokens * p.input * p.cache_write_multiplier
    ) / 1_000_000
    return cost * (BATCH_DISCOUNT if batch else 1.0)


def project_cost(
    model: str,
    n_requests: int,
    system_tokens: int,
    avg_user_tokens: float,
    avg_output_tokens: float,
    cache_hit_rate: float,
    batch: bool | None = None,
) -> float:
    """Projected cost of n requests that share one system prompt.

    If the system prompt is shorter than the model's minimum cacheable length it is
    billed as ordinary input on every request. Otherwise a share `cache_hit_rate` of
    requests read it from cache and the rest pay the miss price.
    """
    if n_requests <= 0:
        return 0.0
    p = PRICES[model]
    batch = p.batch if batch is None else batch
    user_in = n_requests * avg_user_tokens
    out = n_requests * avg_output_tokens
    if system_tokens < p.min_cacheable_tokens:
        return usage_cost(model, user_in + n_requests * system_tokens, out, batch=batch)
    hits = n_requests * cache_hit_rate
    misses = n_requests - hits
    return usage_cost(
        model,
        input_tokens=user_in,
        output_tokens=out,
        cache_read_tokens=hits * system_tokens,
        cache_write_tokens=misses * system_tokens,
        batch=batch,
    )


def within_budget(spent: float, projected: float, budget: float = DEFAULT_BUDGET_USD) -> bool:
    return spent + projected <= budget
