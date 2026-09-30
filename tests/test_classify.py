"""Classifier plumbing that can be tested without calling the API."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

import classify
from prompts import PROMPT_VERSION

MODEL = "claude-opus-5-5"


def fake_message(payload, stop_reason="end_turn", input_tokens=800, output_tokens=400,
                 cache_read=1600, cache_write=0):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                              cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write),
    )


def item(cid, theme="billing"):
    return {"id": str(cid), "primary_theme": theme, "secondary_theme": None,
            "sentiment": "negative", "named_benefits": [], "card_product": None}


def test_make_packs_is_deterministic_and_covers_every_row_once():
    rows = pd.DataFrame({"complaint_id": range(1, 22), "narrative": ["text"] * 21})
    packs = classify.make_packs(rows, pack_size=8)
    assert [len(p) for p in packs] == [8, 8, 5]
    assert sorted(pd.concat(packs)["complaint_id"]) == list(range(1, 22))
    again = classify.make_packs(rows, pack_size=8)
    assert [list(p["complaint_id"]) for p in packs] == [list(p["complaint_id"]) for p in again]


def test_request_uses_structured_output_caching_and_low_effort():
    pack = pd.DataFrame({"complaint_id": [11, 12], "narrative": ["late fee", "lounge closed"]})
    params, truncated = classify.request_params(MODEL, pack)
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert params["output_config"]["effort"] == "low"
    assert params["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert 'id="11"' in params["messages"][0]["content"] and 'id="12"' in params["messages"][0]["content"]
    assert truncated == {"11": False, "12": False}
    # Haiku 4.5 does not accept the effort setting
    haiku_params, _ = classify.request_params("claude-haiku-4-5", pack)
    assert "effort" not in haiku_params["output_config"]


def test_pack_to_records_splits_usage_and_keeps_item_level_status():
    message = fake_message({"results": [item(1, "annual_fee"), item(3, "not_a_theme")]})
    records = classify.pack_to_records(["1", "2", "3"], {"1": True}, MODEL, message, "batch", "pack-0")
    by_id = {r["complaint_id"]: r for r in records}
    assert by_id[1]["status"] == "ok" and by_id[1]["primary_theme"] == "annual_fee"
    assert by_id[1]["narrative_truncated"] is True
    assert by_id[2]["status"] == "missing_in_response"
    assert by_id[3]["status"] == "parse_error"
    assert sum(r["input_tokens"] for r in records) == pytest.approx(800)
    assert sum(r["output_tokens"] for r in records) == pytest.approx(400)
    assert all(r["prompt_version"] == PROMPT_VERSION and r["pack_id"] == "pack-0" for r in records)


def test_pack_to_records_handles_refusal_and_cut_off_output():
    refused = classify.pack_to_records(["1", "2"], {}, MODEL, fake_message("", "refusal"), "batch", "p")
    assert [r["status"] for r in refused] == ["refusal", "refusal"]
    cut = classify.pack_to_records(["1"], {}, MODEL, fake_message('{"results": [', "max_tokens"), "batch", "p")
    assert cut[0]["status"] == "output_cut_off"


def test_cache_round_trip_spend_and_retry_rules(tmp_path, monkeypatch):
    path = tmp_path / "labels.jsonl"
    monkeypatch.setattr(classify, "LABELS_JSONL", path)
    assert classify.load_cache(path).empty and classify.cached_ids(MODEL, path) == set()

    ok = classify.pack_to_records(["1", "2"], {}, MODEL, fake_message({"results": [item(1), item(2)]}),
                                  "batch", "pack-0")
    failed = [{"complaint_id": 3, "model": MODEL, "prompt_version": PROMPT_VERSION, "mode": "batch",
               "status": "api_error", "input_tokens": 0, "output_tokens": 0,
               "cache_read_tokens": 0, "cache_write_tokens": 0}]
    stale = [{**ok[0], "complaint_id": 4, "prompt_version": "v0"}]
    classify.append_cache(ok + failed + stale, path)

    # api errors are retried, and labels from an older prompt version do not count
    assert classify.cached_ids(MODEL, path) == {1, 2}
    assert classify.cached_ids("claude-haiku-4-5", path) == set()

    cache = classify.load_cache(path)
    expected = (800 * 4.0 + 400 * 20.0 + 1600 * 0.20) / 1e6 * 0.5  # one pack at batch prices
    assert classify.spend_so_far(cache[cache["prompt_version"] == PROMPT_VERSION]) == pytest.approx(expected)


def test_estimate_scales_with_rows_and_orders_scenarios():
    tokens = {"system_tokens": 2000, "avg_user_tokens": 3800}
    low, expected, high = (classify.scenario_cost(MODEL, 4000, tokens, s) for s in ("low", "expected", "high"))
    assert low < expected < high
    assert classify.scenario_cost(MODEL, 8000, tokens, "expected") == pytest.approx(2 * expected)
    assert classify.scenario_cost(MODEL, 0, tokens, "high") == 0.0


def test_missing_key_stops_before_any_api_call(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(classify, "load_dotenv", lambda *a, **k: False)
    with pytest.raises(SystemExit) as exc:
        classify.require_client()
    assert exc.value.code == classify.EXIT_NO_KEY
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().out
