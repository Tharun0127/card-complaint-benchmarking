"""Taxonomy parsing: classifier output is either mapped onto the taxonomy or rejected."""
import json

import pytest

from prompts import MAX_NARRATIVE_CHARS, SYSTEM_PROMPT, build_user_message
from taxonomy import (
    MEMBERSHIP_VALUE_THEMES,
    OUTPUT_SCHEMA,
    THEME_KEYS,
    Classification,
    TaxonomyError,
    normalize_theme,
    parse_classification,
)

VALID = {
    "primary_theme": "annual_fee",
    "secondary_theme": None,
    "sentiment": "negative",
    "named_benefits": [],
    "card_product": None,
}


def test_taxonomy_has_the_ten_requested_themes():
    assert THEME_KEYS == [
        "annual_fee", "statement_credit_benefit", "rewards_points", "lounge_travel_benefit",
        "insurance_protection_claim", "dispute_fraud", "customer_service",
        "credit_limit_account_closure", "billing", "other",
    ]
    assert MEMBERSHIP_VALUE_THEMES < set(THEME_KEYS)


def test_parse_valid_dict_and_json_string():
    assert parse_classification(VALID) == Classification("annual_fee", None, "negative", [], None)
    assert parse_classification(json.dumps(VALID)) == parse_classification(VALID)


def test_parse_json_wrapped_in_prose_or_code_fence():
    wrapped = "Here is the label:\n```json\n" + json.dumps(VALID) + "\n```"
    assert parse_classification(wrapped).primary_theme == "annual_fee"


def test_display_labels_and_loose_formatting_are_normalized():
    assert normalize_theme("Annual fee") == "annual_fee"
    assert normalize_theme(" Statement credit or benefit redemption ") == "statement_credit_benefit"
    assert normalize_theme("Dispute-or-fraud") == "dispute_fraud"
    out = parse_classification({**VALID, "primary_theme": "Rewards and points", "sentiment": "Very negative"})
    assert (out.primary_theme, out.sentiment) == ("rewards_points", "very_negative")


@pytest.mark.parametrize("bad", [
    {**VALID, "primary_theme": "interest_rates"},
    {**VALID, "primary_theme": None},
    {**VALID, "sentiment": "furious"},
    {**VALID, "secondary_theme": "made_up"},
    {**VALID, "named_benefits": 3},
    {k: v for k, v in VALID.items() if k != "primary_theme"},
    "not json at all",
    '{"primary_theme": "annual_fee", ',
    42,
])
def test_invalid_output_is_rejected_not_guessed(bad):
    with pytest.raises(TaxonomyError):
        parse_classification(bad)


def test_secondary_theme_equal_to_primary_is_dropped():
    out = parse_classification({**VALID, "secondary_theme": "annual_fee"})
    assert out.secondary_theme is None


@pytest.mark.parametrize("nullish", [None, "", "null", "None", "N/A", "unknown"])
def test_nullish_strings_become_none(nullish):
    out = parse_classification({**VALID, "secondary_theme": nullish, "card_product": nullish})
    assert out.secondary_theme is None and out.card_product is None


def test_named_benefits_are_cleaned_deduplicated_and_capped():
    raw = ["Uber Cash", "uber cash", "  airline   fee credit ", "", "none", "a", "b", "c", "d"]
    out = parse_classification({**VALID, "named_benefits": raw})
    assert out.named_benefits == ["Uber Cash", "airline fee credit", "a", "b", "c"]
    assert parse_classification({**VALID, "named_benefits": "Priority Pass"}).named_benefits == ["Priority Pass"]


def test_membership_value_flag():
    assert parse_classification({**VALID, "primary_theme": "lounge_travel_benefit"}).is_membership_value
    assert not parse_classification({**VALID, "primary_theme": "dispute_fraud"}).is_membership_value


def test_schema_is_strict_and_matches_taxonomy():
    assert OUTPUT_SCHEMA["additionalProperties"] is False
    assert set(OUTPUT_SCHEMA["required"]) == set(OUTPUT_SCHEMA["properties"])
    assert OUTPUT_SCHEMA["properties"]["primary_theme"]["enum"] == THEME_KEYS


def test_prompt_examples_parse_and_every_theme_is_defined():
    for key in THEME_KEYS:
        assert f"- {key}:" in SYSTEM_PROMPT
    examples = [line for line in SYSTEM_PROMPT.splitlines() if line.startswith('{"primary_theme"')]
    assert len(examples) >= 5
    for line in examples:
        parse_classification(line)


def test_long_narratives_are_cut_and_flagged():
    short, cut_short = build_user_message("My card was charged twice.")
    assert not cut_short and "charged twice" in short
    long_text, cut_long = build_user_message("x" * (MAX_NARRATIVE_CHARS + 500))
    assert cut_long and "cut here for length" in long_text
    assert len(long_text) < MAX_NARRATIVE_CHARS + 200
