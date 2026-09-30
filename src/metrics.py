"""Metric logic shared by the analysis scripts. Pure functions, covered by tests."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


def share(numerator: float, denominator: float) -> float | None:
    """numerator / denominator, or None when the denominator is zero or missing."""
    if denominator is None or denominator == 0 or pd.isna(denominator):
        return None
    return numerator / denominator


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion. Behaves well for small n and rare themes."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def timely_rate(timely_flags: pd.Series) -> float | None:
    """Share of complaints with a timely company response. Blank values are excluded."""
    known = timely_flags.dropna()
    known = known[known.isin(["Yes", "No"])]
    return share((known == "Yes").sum(), len(known))


def weighted_shares(
    df: pd.DataFrame, group_cols: list[str], category_col: str, weight_col: str = "weight"
) -> pd.DataFrame:
    """Category shares within each group using sampling weights.

    The classified sample is stratified by issuer and quarter, so each row stands for
    `weight` complaints in the population. Shares must use the weights, otherwise small
    quarters count as much as large ones.
    """
    totals = df.groupby(group_cols, observed=True)[weight_col].sum().rename("group_weight")
    cells = (
        df.groupby(group_cols + [category_col], observed=True)
        .agg(weight=(weight_col, "sum"), n=(weight_col, "size"))
        .reset_index()
        .merge(totals.reset_index(), on=group_cols)
    )
    cells["share"] = cells["weight"] / cells["group_weight"]
    return cells.drop(columns=["group_weight"])


def effective_sample_size(weights: pd.Series) -> float:
    """Kish effective sample size: how many equal-weight rows the weighted sample is worth."""
    w = weights.astype(float)
    return float(w.sum() ** 2 / (w**2).sum()) if len(w) else 0.0


def months_between(month: pd.Timestamp, event_month: pd.Timestamp) -> int:
    """Whole months from the event month to `month`. The event month itself is 0."""
    return (month.year - event_month.year) * 12 + (month.month - event_month.month)


@dataclass
class DiDResult:
    treated_pre: float
    treated_post: float
    control_pre: float
    control_post: float
    treated_change: float
    control_change: float
    did: float
    se: float
    ci_low: float
    ci_high: float
    n_treated_pre: int
    n_treated_post: int
    n_control_pre: int
    n_control_post: int


def diff_in_diff(
    k_treated_pre: int, n_treated_pre: int,
    k_treated_post: int, n_treated_post: int,
    k_control_pre: int, n_control_pre: int,
    k_control_post: int, n_control_post: int,
    z: float = 1.96,
) -> DiDResult:
    """Difference in differences on shares, with a normal-approximation interval.

    did = (treated_post - treated_pre) - (control_post - control_pre)

    The interval treats complaints as independent draws. It describes sampling noise
    only. It says nothing about whether the comparison group is a valid counterfactual.
    """
    cells = [
        (k_treated_pre, n_treated_pre), (k_treated_post, n_treated_post),
        (k_control_pre, n_control_pre), (k_control_post, n_control_post),
    ]
    if any(n <= 0 for _, n in cells):
        raise ValueError("every cell needs at least one complaint")
    p = [k / n for k, n in cells]
    se = math.sqrt(sum(pi * (1 - pi) / n for pi, (_, n) in zip(p, cells)))
    did = (p[1] - p[0]) - (p[3] - p[2])
    return DiDResult(
        treated_pre=p[0], treated_post=p[1], control_pre=p[2], control_post=p[3],
        treated_change=p[1] - p[0], control_change=p[3] - p[2],
        did=did, se=se, ci_low=did - z * se, ci_high=did + z * se,
        n_treated_pre=n_treated_pre, n_treated_post=n_treated_post,
        n_control_pre=n_control_pre, n_control_post=n_control_post,
    )


def allocate_stratified(available: dict, per_cell: int) -> dict:
    """Rows to draw from each stratum: `per_cell`, or everything if the stratum is smaller."""
    return {key: min(int(n), per_cell) for key, n in available.items()}


def agreement_metrics(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    """Agreement, Cohen's kappa, and precision, recall and F1 per class.

    `y_true` is the human label and `y_pred` the model label. Precision and recall are
    None for a class with no predicted or no true rows, so an empty class is not
    reported as a perfect or a zero score.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred differ in length")
    n = len(y_true)
    if n == 0:
        raise ValueError("no labeled rows")
    agree = sum(t == p for t, p in zip(y_true, y_pred))
    true_counts = {c: sum(t == c for t in y_true) for c in labels}
    pred_counts = {c: sum(p == c for p in y_pred) for c in labels}
    expected = sum(true_counts[c] * pred_counts[c] for c in labels) / (n * n)
    observed = agree / n
    kappa = None if expected == 1 else (observed - expected) / (1 - expected)

    per_class = {}
    for c in labels:
        tp = sum(t == c and p == c for t, p in zip(y_true, y_pred))
        precision = share(tp, pred_counts[c])
        recall = share(tp, true_counts[c])
        f1 = (
            None if precision is None or recall is None or precision + recall == 0
            else 2 * precision * recall / (precision + recall)
        )
        per_class[c] = {"precision": precision, "recall": recall, "f1": f1,
                        "human_n": true_counts[c], "model_n": pred_counts[c]}
    return {"n": n, "agreement": observed, "cohen_kappa": kappa, "per_class": per_class}
