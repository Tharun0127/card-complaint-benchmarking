"""LLM classification of complaint narratives with the Anthropic API.

Commands
  estimate   Project token use and cost for the sample. Makes no billable calls.
  pilot      Classify a few rows with ordinary requests to measure real output tokens.
  run        Submit everything not yet in the cache as a Message Batch, wait, collect.
  collect    Fetch results for a batch that was submitted earlier.
  status     Show cache coverage and spend so far.

Cost controls
  - Results are cached in outputs/llm_labels.jsonl keyed by complaint id, model and
    prompt version. A rerun only sends rows that are not in the cache.
  - `run` refuses to submit if spend so far plus the projection exceeds the budget
    (USD 10 unless --budget is raised on purpose).
  - Batch requests are half price. The shared system prompt is cached.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from config import LABELS_JSONL, LLM_CACHE_DIR, OUTPUT_DIR, ROOT, SAMPLE_PARQUET
from costing import DEFAULT_BUDGET_USD, PRICES, project_cost, usage_cost, within_budget
from prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_message
from taxonomy import OUTPUT_SCHEMA, TaxonomyError, parse_classification

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 2000  # includes thinking tokens on models that think
BATCH_STATE = LLM_CACHE_DIR / "batch_state.json"
COST_ESTIMATE_JSON = OUTPUT_DIR / "cost_estimate.json"

# Planning assumptions used until a pilot has measured the real numbers.
CHARS_PER_TOKEN = 3.3
REQUEST_OVERHEAD_TOKENS = 60
ASSUMED_OUTPUT_TOKENS = {"low": 90, "expected": 250, "high": 500}
ASSUMED_OUTPUT_TOKENS_NO_THINKING = {"low": 70, "expected": 90, "high": 130}
ASSUMED_CACHE_HIT = {"low": 0.95, "expected": 0.7, "high": 0.0}

EXIT_NO_KEY = 3
EXIT_OVER_BUDGET = 2


def model_name() -> str:
    return os.environ.get("CLASSIFY_MODEL", DEFAULT_MODEL)


def has_api_key() -> bool:
    load_dotenv(ROOT / ".env")
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def require_client():
    if not has_api_key():
        print(
            "ANTHROPIC_API_KEY is not set. Set it in the environment or in a .env file at "
            "the project root, then rerun. No API call was made."
        )
        sys.exit(EXIT_NO_KEY)
    import anthropic

    return anthropic.Anthropic()


def request_params(model: str, narrative: str) -> tuple[dict, bool]:
    user_text, truncated = build_user_message(narrative)
    output_config: dict = {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}}
    if PRICES[model].thinks:
        # Thinking cannot be turned off on these models. Low effort keeps it short,
        # which is enough for a single-label classification.
        output_config["effort"] = "low"
    params = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ],
        "messages": [{"role": "user", "content": user_text}],
        "output_config": output_config,
    }
    return params, truncated


# --- cache ------------------------------------------------------------------------------
def load_cache(path: Path = LABELS_JSONL) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(
            columns=["complaint_id", "model", "prompt_version", "status", "mode"]
        )
    return pd.read_json(path, lines=True, dtype={"complaint_id": "int64"})


def cached_ids(model: str, path: Path = LABELS_JSONL) -> set[int]:
    cache = load_cache(path)
    if cache.empty:
        return set()
    hit = cache[(cache["model"] == model) & (cache["prompt_version"] == PROMPT_VERSION)]
    # Rows that errored for a transient reason are retried. Everything else is final.
    return set(hit.loc[hit["status"] != "api_error", "complaint_id"].astype(int))


def append_cache(records: list[dict], path: Path = LABELS_JSONL) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def message_to_record(complaint_id: int, model: str, truncated: bool, message, mode: str) -> dict:
    usage = message.usage
    rec = {
        "complaint_id": int(complaint_id),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "mode": mode,
        "narrative_truncated": bool(truncated),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }
    if message.stop_reason == "refusal":
        return {**rec, "status": "refusal"}
    if message.stop_reason == "max_tokens":
        return {**rec, "status": "output_cut_off"}
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        parsed = parse_classification(text)
    except TaxonomyError as exc:
        return {**rec, "status": "parse_error", "error": str(exc)}
    return {**rec, "status": "ok", **parsed.to_dict()}


def spend_so_far(path: Path = LABELS_JSONL) -> float:
    cache = load_cache(path)
    if cache.empty or "input_tokens" not in cache:
        return 0.0
    total = 0.0
    for (model, mode), grp in cache.groupby(["model", "mode"]):
        total += usage_cost(
            model,
            int(grp["input_tokens"].sum()),
            int(grp["output_tokens"].sum()),
            int(grp["cache_read_tokens"].sum()),
            int(grp["cache_write_tokens"].sum()),
            batch=(mode == "batch"),
        )
    return total


# --- estimate ---------------------------------------------------------------------------
def load_sample() -> pd.DataFrame:
    if not SAMPLE_PARQUET.exists():
        print(f"{SAMPLE_PARQUET} not found. Run src/sample.py first.")
        sys.exit(1)
    return pd.read_parquet(SAMPLE_PARQUET)


def measured_output_tokens(model: str) -> float | None:
    cache = load_cache()
    if cache.empty or "output_tokens" not in cache:
        return None
    hit = cache[(cache["model"] == model) & (cache["prompt_version"] == PROMPT_VERSION)]
    return float(hit["output_tokens"].mean()) if len(hit) >= 20 else None


def token_inputs(sample: pd.DataFrame, client=None, model: str | None = None) -> dict:
    """System prompt tokens and average user tokens, counted by the API when possible."""
    user_texts = [build_user_message(t)[0] for t in sample["narrative"]]
    if client is not None and model is not None:
        system_tokens = client.messages.count_tokens(
            model=model, system=SYSTEM_PROMPT, messages=[{"role": "user", "content": "x"}]
        ).input_tokens
        probe = pd.Series(user_texts).sample(min(60, len(user_texts)), random_state=7)
        counted = [
            client.messages.count_tokens(
                model=model, messages=[{"role": "user", "content": t}]
            ).input_tokens
            for t in probe
        ]
        ratio = sum(len(t) for t in probe) / max(sum(counted), 1)
        avg_user = sum(len(t) for t in user_texts) / len(user_texts) / ratio
        return {"system_tokens": system_tokens, "avg_user_tokens": avg_user,
                "method": f"count_tokens API on {len(probe)} sampled rows, {ratio:.2f} chars per token"}
    avg_user = sum(len(t) for t in user_texts) / len(user_texts) / CHARS_PER_TOKEN
    return {
        "system_tokens": int(len(SYSTEM_PROMPT) / CHARS_PER_TOKEN),
        "avg_user_tokens": avg_user + REQUEST_OVERHEAD_TOKENS,
        "method": f"heuristic, {CHARS_PER_TOKEN} characters per token (no API key available)",
    }


def build_estimate(sample: pd.DataFrame, n_remaining: dict[str, int], tokens: dict) -> dict:
    out: dict = {
        "sample_rows": len(sample),
        "prompt_version": PROMPT_VERSION,
        "token_method": tokens["method"],
        "system_prompt_tokens": int(tokens["system_tokens"]),
        "avg_user_tokens_per_request": round(tokens["avg_user_tokens"], 1),
        "narratives_cut_for_length": int((sample["narrative"].str.len() > 6000).sum()),
        "budget_usd": DEFAULT_BUDGET_USD,
        "models": {},
    }
    for model, price in PRICES.items():
        measured = measured_output_tokens(model)
        assumed = ASSUMED_OUTPUT_TOKENS if price.thinks else ASSUMED_OUTPUT_TOKENS_NO_THINKING
        scenarios = {}
        for name in ("low", "expected", "high"):
            out_tokens = measured if measured is not None else assumed[name]
            scenarios[name] = round(
                project_cost(model, n_remaining[model], tokens["system_tokens"],
                             tokens["avg_user_tokens"], out_tokens, ASSUMED_CACHE_HIT[name]), 2)
        out["models"][model] = {
            "requests_not_in_cache": n_remaining[model],
            "output_tokens_per_request": (
                {"measured_in_pilot": round(measured, 1)} if measured is not None else assumed
            ),
            "system_prompt_cacheable": tokens["system_tokens"] >= price.min_cacheable_tokens,
            "batch_cost_usd": scenarios,
            "within_budget_at_high": scenarios["high"] <= DEFAULT_BUDGET_USD,
        }
    return out


def cmd_estimate(args) -> int:
    sample = load_sample()
    client = None
    if has_api_key():
        import anthropic

        client = anthropic.Anthropic()
    tokens = token_inputs(sample, client, model_name() if client else None)
    remaining = {m: len(set(sample["complaint_id"]) - cached_ids(m)) for m in PRICES}
    est = build_estimate(sample, remaining, tokens)
    est["spent_so_far_usd"] = round(spend_so_far(), 4)
    COST_ESTIMATE_JSON.write_text(json.dumps(est, indent=2), encoding="utf-8")
    print(json.dumps(est, indent=2))
    return 0


# --- pilot ------------------------------------------------------------------------------
def cmd_pilot(args) -> int:
    client = require_client()
    model = model_name()
    sample = load_sample()
    todo = sample[~sample["complaint_id"].isin(cached_ids(model))]
    todo = todo.sample(min(args.n, len(todo)), random_state=11)
    # A pilot is tiny, but the same budget rule applies.
    tokens = token_inputs(todo, client, model)
    projected = project_cost(model, len(todo), tokens["system_tokens"], tokens["avg_user_tokens"],
                             ASSUMED_OUTPUT_TOKENS["high"], 0.0, batch=False)
    if not within_budget(spend_so_far(), projected, args.budget):
        print(f"Pilot would exceed the budget (projected {projected:.2f} USD). Not sent.")
        return EXIT_OVER_BUDGET
    for row in todo.itertuples():
        params, truncated = request_params(model, row.narrative)
        message = client.messages.create(**params)
        append_cache([message_to_record(row.complaint_id, model, truncated, message, "pilot")])
    cache = load_cache()
    pilot = cache[(cache["model"] == model) & (cache["mode"] == "pilot")]
    print(f"pilot rows: {len(pilot)} | status: {pilot['status'].value_counts().to_dict()}")
    print(f"avg output tokens: {pilot['output_tokens'].mean():.0f} | "
          f"cache reads on {int((pilot['cache_read_tokens'] > 0).sum())} of {len(pilot)} requests")
    print(f"spend so far: {spend_so_far():.4f} USD")
    return 0


# --- batch run --------------------------------------------------------------------------
def submit_batch(client, model: str, todo: pd.DataFrame) -> dict:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    requests, truncated_flags = [], {}
    for row in todo.itertuples():
        params, truncated = request_params(model, row.narrative)
        truncated_flags[str(row.complaint_id)] = truncated
        requests.append(
            Request(custom_id=str(row.complaint_id), params=MessageCreateParamsNonStreaming(**params))
        )
    batch = client.messages.batches.create(requests=requests)
    state = {"batch_id": batch.id, "model": model, "prompt_version": PROMPT_VERSION,
             "n_requests": len(requests), "truncated": truncated_flags, "collected": False}
    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_STATE.write_text(json.dumps(state), encoding="utf-8")
    print(f"submitted batch {batch.id} with {len(requests)} requests")
    return state


def wait_and_collect(client, state: dict, poll_seconds: int = 60) -> None:
    while True:
        batch = client.messages.batches.retrieve(state["batch_id"])
        if batch.processing_status == "ended":
            break
        c = batch.request_counts
        print(f"batch {batch.id}: processing {c.processing}, succeeded {c.succeeded}, errored {c.errored}")
        time.sleep(poll_seconds)

    records = []
    for result in client.messages.batches.results(state["batch_id"]):
        cid = int(result.custom_id)
        if result.result.type == "succeeded":
            records.append(message_to_record(
                cid, state["model"], state["truncated"].get(result.custom_id, False),
                result.result.message, "batch"))
        else:
            # errored, canceled or expired: nothing was billed, and the row is retried next run
            records.append({"complaint_id": cid, "model": state["model"],
                            "prompt_version": state["prompt_version"], "mode": "batch",
                            "status": "api_error", "error": result.result.type,
                            "input_tokens": 0, "output_tokens": 0,
                            "cache_read_tokens": 0, "cache_write_tokens": 0})
    append_cache(records)
    state["collected"] = True
    BATCH_STATE.write_text(json.dumps(state), encoding="utf-8")
    ok = sum(r["status"] == "ok" for r in records)
    print(f"collected {len(records)} results, {ok} ok | spend so far: {spend_so_far():.4f} USD")


def pending_batch() -> dict | None:
    if not BATCH_STATE.exists():
        return None
    state = json.loads(BATCH_STATE.read_text(encoding="utf-8"))
    return None if state.get("collected") else state


def cmd_run(args) -> int:
    client = require_client()
    model = model_name()
    # Never submit twice: if an earlier batch has not been collected, finish that one.
    state = pending_batch()
    if state:
        print(f"resuming uncollected batch {state['batch_id']}")
        wait_and_collect(client, state)

    sample = load_sample()
    todo = sample[~sample["complaint_id"].isin(cached_ids(model))]
    if todo.empty:
        print("Every sampled row is already in the cache. No API calls needed.")
        return 0

    tokens = token_inputs(todo, client, model)
    measured = measured_output_tokens(model)
    out_tokens = measured if measured is not None else ASSUMED_OUTPUT_TOKENS["high"]
    # Budget check uses the pessimistic case: no cache hits at all.
    projected = project_cost(model, len(todo), tokens["system_tokens"],
                             tokens["avg_user_tokens"], out_tokens, cache_hit_rate=0.0)
    spent = spend_so_far()
    print(f"model {model} | rows to send {len(todo)} | spent {spent:.2f} USD | "
          f"projected (no cache hits) {projected:.2f} USD | budget {args.budget:.2f} USD")
    if not within_budget(spent, projected, args.budget):
        print("Projected total exceeds the budget. Nothing was sent. Raise --budget only "
              "with explicit approval, reduce the sample, or choose a cheaper CLASSIFY_MODEL.")
        return EXIT_OVER_BUDGET
    wait_and_collect(client, submit_batch(client, model, todo))
    return 0


def cmd_collect(args) -> int:
    client = require_client()
    state = pending_batch()
    if not state:
        print("No uncollected batch.")
        return 0
    wait_and_collect(client, state)
    return 0


def cmd_status(args) -> int:
    cache = load_cache()
    print(f"cache rows: {len(cache)} | spend so far: {spend_so_far():.4f} USD")
    if not cache.empty:
        print(cache.groupby(["model", "prompt_version", "mode", "status"]).size().to_string())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("estimate").set_defaults(func=cmd_estimate)
    p = sub.add_parser("pilot")
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--budget", type=float, default=DEFAULT_BUDGET_USD)
    p.set_defaults(func=cmd_pilot)
    p = sub.add_parser("run")
    p.add_argument("--budget", type=float, default=DEFAULT_BUDGET_USD)
    p.set_defaults(func=cmd_run)
    sub.add_parser("collect").set_defaults(func=cmd_collect)
    sub.add_parser("status").set_defaults(func=cmd_status)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
