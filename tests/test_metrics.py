"""Metric logic: shares, intervals, sampling weights, difference in differences, agreement."""
import math

import pandas as pd
import pytest

from costing import PRICES, project_cost, usage_cost, within_budget
from metrics import (
    agreement_metrics,
    allocate_stratified,
    diff_in_diff,
    effective_sample_size,
    months_between,
    share,
    timely_rate,
    weighted_shares,
    wilson_interval,
)


def test_share_handles_zero_and_missing_denominator():
    assert share(1, 4) == 0.25
    assert share(1, 0) is None
    assert share(1, float("nan")) is None


def test_wilson_interval_known_value_and_bounds():
    low, high = wilson_interval(10, 100)
    assert low == pytest.approx(0.0552, abs=5e-4) and high == pytest.approx(0.1744, abs=5e-4)
    assert wilson_interval(0, 20)[0] == 0.0
    assert wilson_interval(20, 20)[1] == 1.0
    assert all(math.isnan(x) for x in wilson_interval(0, 0))


def test_timely_rate_ignores_blanks():
    flags = pd.Series(["Yes", "Yes", "No", None, "Yes"])
    assert timely_rate(flags) == 0.75
    assert timely_rate(pd.Series([None, None], dtype=object)) is None


def test_weighted_shares_differ_from_raw_shares():
    # Quarter A: 1,000 complaints, 2 sampled, both fee. Quarter B: 100 complaints, 2 sampled, none fee.
    df = pd.DataFrame({
        "issuer": ["X"] * 4,
        "theme": ["fee", "fee", "other", "other"],
        "weight": [500.0, 500.0, 50.0, 50.0],
    })
    out = weighted_shares(df, ["issuer"], "theme").set_index("theme")
    assert out.loc["fee", "share"] == pytest.approx(1000 / 1100)  # raw share would be 0.5
    assert out.loc["fee", "n"] == 2
    assert out["share"].sum() == pytest.approx(1.0)


def test_effective_sample_size():
    assert effective_sample_size(pd.Series([1.0] * 10)) == pytest.approx(10)
    assert effective_sample_size(pd.Series([9.0, 1.0])) == pytest.approx(100 / 82)


def test_months_between():
    event = pd.Timestamp("2025-09-01")
    assert months_between(pd.Timestamp("2025-09-01"), event) == 0
    assert months_between(pd.Timestamp("2025-06-01"), event) == -3
    assert months_between(pd.Timestamp("2026-02-01"), event) == 5


def test_diff_in_diff_arithmetic():
    r = diff_in_diff(10, 100, 30, 100, 20, 200, 24, 200)
    assert r.treated_change == pytest.approx(0.20)
    assert r.control_change == pytest.approx(0.02)
    assert r.did == pytest.approx(0.18)
    expected_se = math.sqrt(0.1 * 0.9 / 100 + 0.3 * 0.7 / 100 + 0.1 * 0.9 / 200 + 0.12 * 0.88 / 200)
    assert r.se == pytest.approx(expected_se)
    assert r.ci_low < r.did < r.ci_high


def test_diff_in_diff_is_zero_when_both_groups_move_together():
    assert diff_in_diff(10, 100, 20, 100, 50, 500, 100, 500).did == pytest.approx(0.0)


def test_diff_in_diff_rejects_empty_cells():
    with pytest.raises(ValueError):
        diff_in_diff(0, 0, 1, 10, 1, 10, 1, 10)


def test_allocate_stratified_caps_at_available():
    assert allocate_stratified({"a": 500, "b": 12, "c": 0}, 45) == {"a": 45, "b": 12, "c": 0}


def test_agreement_metrics_on_a_known_confusion_matrix():
    human = ["fee"] * 4 + ["fraud"] * 4 + ["other"] * 2
    model = ["fee", "fee", "fee", "fraud", "fraud", "fraud", "fraud", "fraud", "other", "fee"]
    m = agreement_metrics(human, model, ["fee", "fraud", "other", "unused"])
    assert m["n"] == 10 and m["agreement"] == pytest.approx(0.8)
    assert m["per_class"]["fee"]["precision"] == pytest.approx(3 / 4)
    assert m["per_class"]["fee"]["recall"] == pytest.approx(3 / 4)
    assert m["per_class"]["fraud"]["precision"] == pytest.approx(4 / 5)
    assert m["per_class"]["fraud"]["recall"] == pytest.approx(1.0)
    assert m["per_class"]["other"]["recall"] == pytest.approx(0.5)
    # expected agreement = (4*4 + 4*5 + 2*1) / 100 = 0.38
    assert m["cohen_kappa"] == pytest.approx((0.8 - 0.38) / (1 - 0.38))
    # a class nobody used has no precision or recall, not a fake 0 or 1
    assert m["per_class"]["unused"]["precision"] is None
    assert m["per_class"]["unused"]["recall"] is None


def test_agreement_metrics_validates_input():
    with pytest.raises(ValueError):
        agreement_metrics(["a"], ["a", "b"], ["a", "b"])
    with pytest.raises(ValueError):
        agreement_metrics([], [], ["a"])


# --- cost logic ---------------------------------------------------------------------------
def test_usage_cost_applies_batch_discount_and_cache_prices():
    # 1M uncached input + 1M output on Opus 5.5 at list price, then at batch price
    assert usage_cost("claude-opus-5-5", 1_000_000, 1_000_000, batch=False) == pytest.approx(24.0)
    assert usage_cost("claude-opus-5-5", 1_000_000, 1_000_000, batch=True) == pytest.approx(12.0)
    # cache read at 0.20 per million, 1-hour cache write at 2x input
    assert usage_cost("claude-opus-5-5", 0, 0, cache_read_tokens=1_000_000, batch=False) == pytest.approx(0.20)
    assert usage_cost("claude-opus-5-5", 0, 0, cache_write_tokens=1_000_000, batch=False) == pytest.approx(8.0)


def test_project_cost_caching_lowers_cost_only_when_prompt_is_long_enough():
    kwargs = dict(n_requests=1000, system_tokens=1500, avg_user_tokens=400, avg_output_tokens=200)
    no_hits = project_cost("claude-opus-5-5", cache_hit_rate=0.0, **kwargs)
    all_hits = project_cost("claude-opus-5-5", cache_hit_rate=1.0, **kwargs)
    assert all_hits < no_hits
    # Haiku 4.5 needs 4,096 tokens to cache, so a 1,500-token prompt is billed as plain input
    assert PRICES["claude-haiku-4-5"].min_cacheable_tokens > 1500
    haiku_a = project_cost("claude-haiku-4-5", cache_hit_rate=0.0, **kwargs)
    haiku_b = project_cost("claude-haiku-4-5", cache_hit_rate=1.0, **kwargs)
    assert haiku_a == haiku_b == pytest.approx((1000 * 1900 * 1.0 + 1000 * 200 * 5.0) / 1e6 * 0.5)
    assert project_cost("claude-opus-5-5", 0, 1500, 400, 200, 0.5) == 0.0


def test_budget_guard():
    assert within_budget(spent=2.0, projected=7.9)
    assert not within_budget(spent=2.0, projected=8.1)
    assert within_budget(spent=0.0, projected=10.0)
    assert not within_budget(spent=0.0, projected=12.0, budget=10.0)
