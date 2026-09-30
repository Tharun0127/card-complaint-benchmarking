"""LLM classification of complaint narratives with the Anthropic API.

Commands
  estimate   Project token use and cost for the sample. Makes no billable calls.
  pilot      Classify a few packs with ordinary requests to measure real token use.
  run        Send everything not yet in the cache as Message Batches, wait, collect.
  collect    Fetch results for a batch that was submitted earlier.
  status     Show cache coverage and spend so far.

Cost controls
  - Results are cached in outputs/llm_labels.jsonl keyed by complaint id, model and
    prompt version. A rerun only sends rows that are not in the cache.
  - Three levers keep the unit cost down: the Message Batches API (half price), prompt
    caching on the shared system prompt, and packing PACK_SIZE complaints into each
    request so the system prompt and any thinking are paid once per pack.
  - `run` sends the sample in chunks. Before each chunk it checks two things against the
    budget (USD 10 unless --budget is raised on purpose): the worst case for that chunk,
    and the projection for everything left using token use measured so far. If either
    fails, nothing more is sent and the command exits with code 2.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from config import LABELS_JSONL, LLM_CACHE_DIR, OUTPUT_DIR, ROOT, SAMPLE_PARQUET
from costing import DEFAULT_BUDGET_USD, PRICES, project_cost, usage_cost, within_budget
from prompts import MAX_NARRATIVE_CHARS, PROMPT_VERSION, SYSTEM_PROMPT, build_user_message
from taxonomy import OUTPUT_SCHEMA, TaxonomyError, parse_pack

DEFAULT_MODEL = "claude-opus-5-5"
PACK_SIZE = 8
MAX_TOKENS = 4000  # per pack, and includes thinking tokens on models that think
PACK_SEED = 17
BATCH_STATE = LLM_CACHE_DIR / "batch_state.json"
COST_ESTIMATE_JSON = OUTPUT_DIR / "cost_estimate.json"
FIRST_CHUNK_ROWS = 320
CHUNK_ROWS = 2000
USAGE_COLS = ["input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"]
RETRYABLE = {"api_error", "missing_in_response"}

# Planning assumptions, used only until a pilot or a first chunk has measured real numbers.
CHARS_PER_TOKEN = 3.3
PACK_OVERHEAD_TOKENS = 40
ITEM_OUTPUT_TOKENS = {"low": 60, "expected": 75, "high": 100}
THINKING_TOKENS_PER_PACK = {"low": 0, "expected": 300, "high": 1200}
CACHE_HIT = {"low": 0.95, "expected": 0.7, "high": 0.0}
SCENARIOS = {
    "low": "95% cache hits, short outputs, no thinking",
    "expected": "70% cache hits, typical outputs, some thinking",
    "high": "no cache hits, long outputs, heavy thinking",
}

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


def make_packs(rows: pd.DataFrame, pack_size: int = PACK_SIZE, seed: int = PACK_SEED) -> list[pd.DataFrame]:
    """Shuffle rows and cut them into packs, so a pack mixes issuers and quarters."""
    shuffled = rows.sample(frac=1.0, random_state=seed)
    return [shuffled.iloc[i:i + pack_size] for i in range(0, len(shuffled), pack_size)]


def request_params(model: str, pack: pd.DataFrame) -> tuple[dict, dict[str, bool]]:
    user_text, truncated = build_user_message(list(zip(pack["complaint_id"], pack["narrative"])))
    output_config: dict = {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}}
    if PRICES[model].thinks:
        # Thinking cannot be turned off on these models. Low effort keeps it short,
        # which is enough for single-label classification.
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
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["complaint_id", "model", "prompt_version", "status", "mode", *USAGE_COLS])
    return pd.read_json(path, lines=True, dtype={"complaint_id": "int64"})


def current(cache: pd.DataFrame, model: str) -> pd.DataFrame:
    return cache[(cache["model"] == model) & (cache["prompt_version"] == PROMPT_VERSION)]


def cached_ids(model: str, path: Path = LABELS_JSONL) -> set[int]:
    hit = current(load_cache(path), model)
    # Rows that failed for a transient reason are retried. Everything else is final.
    return set(hit.loc[~hit["status"].isin(RETRYABLE), "complaint_id"].astype(int))


def append_cache(records: list[dict], path: Path = LABELS_JSONL) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def pack_to_records(ids: list[str], truncated: dict[str, bool], model: str, message, mode: str,
                    pack_id: str) -> list[dict]:
    """One cache record per complaint. The pack's token usage is split evenly across them."""
    usage = message.usage
    n = len(ids)
    shared = {
        "model": model, "prompt_version": PROMPT_VERSION, "mode": mode, "pack_id": pack_id,
        "input_tokens": usage.input_tokens / n,
        "output_tokens": usage.output_tokens / n,
        "cache_read_tokens": (getattr(usage, "cache_read_input_tokens", 0) or 0) / n,
        "cache_write_tokens": (getattr(usage, "cache_creation_input_tokens", 0) or 0) / n,
    }

    def base(cid: str) -> dict:
        return {"complaint_id": int(cid), **shared, "narrative_truncated": bool(truncated.get(cid, False))}

    if message.stop_reason == "refusal":
        return [{**base(c), "status": "refusal"} for c in ids]
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        parsed = parse_pack(text, ids)
    except TaxonomyError as exc:
        status = "output_cut_off" if message.stop_reason == "max_tokens" else "parse_error"
        return [{**base(c), "status": status, "error": str(exc)} for c in ids]

    records = []
    for cid in ids:
        result = parsed[cid]
        if isinstance(result, TaxonomyError):
            missing = "missing" in str(result)
            records.append({**base(cid), "status": "missing_in_response" if missing else "parse_error",
                            "error": str(result)})
        else:
            records.append({**base(cid), "status": "ok", **result.to_dict()})
    return records


def spend_so_far(cache: pd.DataFrame | None = None) -> float:
    cache = load_cache() if cache is None else cache
    total = 0.0
    for (model, mode), grp in cache.groupby(["model", "mode"]):
        total += usage_cost(model, *(grp[c].sum() for c in USAGE_COLS), batch=(mode == "batch"))
    return total


def measured_cost_per_row(model: str, cache: pd.DataFrame | None = None) -> float | None:
    """Average batch-price cost per complaint from real usage, once 40 or more rows exist."""
    cache = load_cache() if cache is None else cache
    billed = current(cache, model)
    billed = billed[billed["status"] != "api_error"]
    if len(billed) < 40:
        return None
    return usage_cost(model, *(billed[c].sum() for c in USAGE_COLS), batch=True) / len(billed)


# --- estimate ---------------------------------------------------------------------------
def load_sample() -> pd.DataFrame:
    if not SAMPLE_PARQUET.exists():
        print(f"{SAMPLE_PARQUET} not found. Run src/sample.py first.")
        sys.exit(1)
    return pd.read_parquet(SAMPLE_PARQUET)


def token_inputs(sample: pd.DataFrame, client=None, model: str | None = None) -> dict:
    """System prompt tokens and average user tokens per pack, counted by the API when possible."""
    packs = make_packs(sample)
    texts = [build_user_message(list(zip(p["complaint_id"], p["narrative"])))[0] for p in packs]
    avg_chars = sum(len(t) for t in texts) / len(texts)
    if client is not None and model is not None:
        system_tokens = client.messages.count_tokens(
            model=model, system=SYSTEM_PROMPT, messages=[{"role": "user", "content": "x"}]
        ).input_tokens
        probe = texts[:20]
        counted = sum(
            client.messages.count_tokens(model=model, messages=[{"role": "user", "content": t}]).input_tokens
            for t in probe
        )
        ratio = sum(len(t) for t in probe) / max(counted, 1)
        return {"system_tokens": system_tokens, "avg_user_tokens": avg_chars / ratio,
                "method": f"count_tokens API on {len(probe)} packs ({ratio:.2f} characters per token)"}
    return {
        "system_tokens": int(len(SYSTEM_PROMPT) / CHARS_PER_TOKEN),
        "avg_user_tokens": avg_chars / CHARS_PER_TOKEN + PACK_OVERHEAD_TOKENS,
        "method": f"heuristic of {CHARS_PER_TOKEN} characters per token (no API key, so tokens were not counted)",
    }


def scenario_cost(model: str, n_rows: int, tokens: dict, scenario: str) -> float:
    n_packs = math.ceil(n_rows / PACK_SIZE)
    thinking = THINKING_TOKENS_PER_PACK[scenario] if PRICES[model].thinks else 0
    out_per_pack = PACK_SIZE * ITEM_OUTPUT_TOKENS[scenario] + thinking
    return project_cost(model, n_packs, tokens["system_tokens"], tokens["avg_user_tokens"],
                        out_per_pack, CACHE_HIT[scenario])


def build_estimate(sample: pd.DataFrame, n_remaining: dict[str, int], tokens: dict) -> dict:
    out: dict = {
        "sample_rows": len(sample),
        "complaints_per_request": PACK_SIZE,
        "requests": math.ceil(len(sample) / PACK_SIZE),
        "prompt_version": PROMPT_VERSION,
        "token_method": tokens["method"],
        "system_prompt_tokens": int(tokens["system_tokens"]),
        "avg_user_tokens_per_request": round(tokens["avg_user_tokens"], 1),
        "narratives_cut_for_length": int((sample["narrative"].str.len() > MAX_NARRATIVE_CHARS).sum()),
        "budget_usd": DEFAULT_BUDGET_USD,
        "scenarios": SCENARIOS,
        "models": {},
    }
    cache = load_cache()
    for model, price in PRICES.items():
        n = n_remaining[model]
        scenarios = {name: round(scenario_cost(model, n, tokens, name), 2) for name in SCENARIOS}
        entry = {
            "rows_not_in_cache": n,
            "system_prompt_long_enough_to_cache": tokens["system_tokens"] >= price.min_cacheable_tokens,
            "batch_cost_usd": scenarios,
            "within_budget_in_every_scenario": scenarios["high"] <= DEFAULT_BUDGET_USD,
        }
        measured = measured_cost_per_row(model, cache)
        if measured is not None:
            entry["measured_cost_per_row_usd"] = round(measured, 5)
            entry["projection_from_measured_usd"] = round(measured * n, 2)
        out["models"][model] = entry
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
def classify_now(client, model: str, packs: list[pd.DataFrame], mode: str) -> None:
    for pack in packs:
        params, truncated = request_params(model, pack)
        message = client.messages.create(**params)
        ids = [str(c) for c in pack["complaint_id"]]
        append_cache(pack_to_records(ids, truncated, model, message, mode, f"{mode}-{ids[0]}"))


def cmd_pilot(args) -> int:
    client = require_client()
    model = model_name()
    sample = load_sample()
    todo = sample[~sample["complaint_id"].isin(cached_ids(model))]
    packs = make_packs(todo)[: args.packs]
    if not packs:
        print("Nothing left to classify.")
        return 0
    n_rows = sum(len(p) for p in packs)
    tokens = token_inputs(todo, client, model)
    # Ordinary requests are full price, so the batch worst case is doubled.
    if not within_budget(spend_so_far(), 2 * scenario_cost(model, n_rows, tokens, "high"), args.budget):
        print("The pilot could exceed the budget. Nothing was sent.")
        return EXIT_OVER_BUDGET
    classify_now(client, model, packs, "pilot")
    pilot = current(load_cache(), model)
    pilot = pilot[pilot["mode"] == "pilot"]
    print(f"pilot rows: {len(pilot)} | status: {pilot['status'].value_counts().to_dict()}")
    print(f"average output tokens per complaint: {pilot['output_tokens'].mean():.0f} | "
          f"rows served with a cache read: {int((pilot['cache_read_tokens'] > 0).sum())} of {len(pilot)}")
    print(f"spend so far: {spend_so_far():.4f} USD")
    return 0


# --- batch run --------------------------------------------------------------------------
def submit_batch(client, model: str, packs: list[pd.DataFrame]) -> dict:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    requests, members, truncated_all = [], {}, {}
    for i, pack in enumerate(packs):
        params, truncated = request_params(model, pack)
        pack_id = f"pack-{i:04d}-{int(pack['complaint_id'].iloc[0])}"
        members[pack_id] = [str(c) for c in pack["complaint_id"]]
        truncated_all.update(truncated)
        requests.append(Request(custom_id=pack_id, params=MessageCreateParamsNonStreaming(**params)))
    batch = client.messages.batches.create(requests=requests)
    state = {"batch_id": batch.id, "model": model, "prompt_version": PROMPT_VERSION,
             "members": members, "truncated": truncated_all, "collected": False}
    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_STATE.write_text(json.dumps(state), encoding="utf-8")
    print(f"submitted batch {batch.id}: {len(requests)} requests, {sum(map(len, members.values()))} complaints")
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
        ids = state["members"][result.custom_id]
        if result.result.type == "succeeded":
            records += pack_to_records(ids, state["truncated"], state["model"],
                                       result.result.message, "batch", result.custom_id)
        else:
            # errored, canceled or expired: nothing was billed, and the rows are retried next run
            records += [{"complaint_id": int(c), "model": state["model"],
                         "prompt_version": state["prompt_version"], "mode": "batch",
                         "pack_id": result.custom_id, "status": "api_error",
                         "error": result.result.type, **{u: 0 for u in USAGE_COLS}} for c in ids]
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
    # Never submit twice: if an earlier batch has not been collected, finish that one first.
    state = pending_batch()
    if state:
        print(f"resuming uncollected batch {state['batch_id']}")
        wait_and_collect(client, state)

    sample = load_sample()
    first, previous_left = True, None
    while True:
        todo = sample[~sample["complaint_id"].isin(cached_ids(model))]
        if todo.empty:
            print("Every sampled row is in the cache. No further API calls needed.")
            return 0
        if previous_left is not None and len(todo) >= previous_left:
            print(f"{len(todo)} rows still have no label after a retry. Stopping so they are not "
                  "paid for again. Check `status` for the reasons.")
            return 1
        previous_left = len(todo)

        per_row = measured_cost_per_row(model)
        chunk = todo.head(FIRST_CHUNK_ROWS if per_row is None else CHUNK_ROWS)
        tokens = token_inputs(todo, client, model)
        spent = spend_so_far()
        chunk_worst = scenario_cost(model, len(chunk), tokens, "high")
        projected_all = per_row * len(todo) if per_row is not None else None
        print(f"model {model} | rows left {len(todo)} | next chunk {len(chunk)} | spent {spent:.2f} USD | "
              f"chunk worst case {chunk_worst:.2f} USD | projection for all remaining "
              f"{'not measured yet' if projected_all is None else f'{projected_all:.2f} USD'} | "
              f"budget {args.budget:.2f} USD")
        over = not within_budget(spent, chunk_worst, args.budget) or (
            projected_all is not None and not within_budget(spent, projected_all, args.budget))
        if over:
            print("Continuing could exceed the budget, so nothing more was sent. Options: raise "
                  "--budget with explicit approval, reduce the sample, or set CLASSIFY_MODEL to "
                  "a cheaper model.")
            return EXIT_OVER_BUDGET

        packs = make_packs(chunk)
        if first:
            # One ordinary request writes the system prompt to the cache before the batch starts.
            classify_now(client, model, packs[:1], "warmup")
            packs = packs[1:]
            first = False
        if packs:
            wait_and_collect(client, submit_batch(client, model, packs))


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
    print(f"cache rows: {len(cache)} | spend so far: {spend_so_far(cache):.4f} USD")
    if not cache.empty:
        print(cache.groupby(["model", "prompt_version", "mode", "status"]).size().to_string())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("estimate").set_defaults(func=cmd_estimate)
    p = sub.add_parser("pilot")
    p.add_argument("--packs", type=int, default=5)
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
