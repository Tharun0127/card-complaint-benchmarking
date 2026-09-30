"""Token and cost arithmetic for the classifier. Pure functions, covered by tests.

Prices are USD per million tokens, from the Anthropic price list as of 25 Sep 2026.
Batch requests are billed at half price. A 1-hour cache write costs 2x the input price.
"""
from __future__ import annotations

from dataclasses import dataclass

BATCH_DISCOUNT = 0.5
CACHE_WRITE_1H_MULTIPLIER = 2.0
DEFAULT_BUDGET_USD = 10.0


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float
    cache_read: float
    min_cacheable_tokens: int
    thinks: bool  # thinking tokens are billed as output and cannot be switched off


PRICES: dict[str, ModelPrice] = {
    "claude-opus-5-5": ModelPrice(4.00, 20.00, 0.20, 512, True),
    "claude-sonnet-5-5": ModelPrice(2.00, 10.00, 0.20, 512, True),
    "claude-haiku-4-5": ModelPrice(1.00, 5.00, 0.10, 4096, False),
}


def usage_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    batch: bool = True,
) -> float:
    """Cost in USD of one or more requests given their token usage.

    `input_tokens` is the uncached input only, which is how the API reports it.
    """
    p = PRICES[model]
    cost = (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_read_tokens * p.cache_read
        + cache_write_tokens * p.input * CACHE_WRITE_1H_MULTIPLIER
    ) / 1_000_000
    return cost * (BATCH_DISCOUNT if batch else 1.0)


def project_cost(
    model: str,
    n_requests: int,
    system_tokens: int,
    avg_user_tokens: float,
    avg_output_tokens: float,
    cache_hit_rate: float,
    batch: bool = True,
) -> float:
    """Projected cost of n requests that share one system prompt.

    If the system prompt is shorter than the model's minimum cacheable length it is
    billed as ordinary input on every request. Otherwise a share `cache_hit_rate` of
    requests read it from cache and the rest write it.
    """
    if n_requests <= 0:
        return 0.0
    p = PRICES[model]
    user_in = n_requests * avg_user_tokens
    out = n_requests * avg_output_tokens
    if system_tokens < p.min_cacheable_tokens:
        return usage_cost(model, int(user_in + n_requests * system_tokens), int(out), batch=batch)
    hits = n_requests * cache_hit_rate
    misses = n_requests - hits
    return usage_cost(
        model,
        input_tokens=int(user_in),
        output_tokens=int(out),
        cache_read_tokens=int(hits * system_tokens),
        cache_write_tokens=int(misses * system_tokens),
        batch=batch,
    )


def within_budget(spent: float, projected: float, budget: float = DEFAULT_BUDGET_USD) -> bool:
    return spent + projected <= budget
