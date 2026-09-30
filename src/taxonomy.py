"""Membership-focused complaint taxonomy and the parser for classifier output.

The taxonomy is the single source of truth for the LLM prompt, the JSON schema, the
fallback classifier, the validation script and the dashboard labels.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

# key -> (display label, definition used in the prompt)
THEMES: dict[str, tuple[str, str]] = {
    "annual_fee": (
        "Annual fee",
        "The annual or membership fee itself: a fee increase, being charged the fee "
        "unexpectedly, a refund or proration of the fee after closing or downgrading, "
        "or the fee not matching what was advertised.",
    ),
    "statement_credit_benefit": (
        "Statement credit or benefit redemption",
        "A card benefit that is delivered as a credit or perk and did not work as "
        "expected: airline, hotel, dining, rideshare, streaming or retail statement "
        "credits, companion certificates, free night awards, enrollment requirements, "
        "or a credit that did not post.",
    ),
    "rewards_points": (
        "Rewards and points",
        "Points, miles or cash back: a welcome or sign-up bonus not awarded, points "
        "forfeited or clawed back, redemption problems, transfer problems, or earning "
        "rates that differ from what was promised.",
    ),
    "lounge_travel_benefit": (
        "Lounge or travel benefit",
        "Airport lounge access, guest policies, travel portal bookings made through "
        "the issuer, hotel status or upgrades, Global Entry or TSA PreCheck credits, "
        "or concierge and travel service problems.",
    ),
    "insurance_protection_claim": (
        "Insurance or protection claim",
        "A claim under a card protection: purchase protection, extended warranty, "
        "return protection, trip delay or cancellation, baggage, rental car or cell "
        "phone coverage, including denied or slow claims and benefit administrators.",
    ),
    "dispute_fraud": (
        "Dispute or fraud",
        "A disputed transaction, a merchant dispute or chargeback decision, "
        "unauthorized charges, identity theft, an account opened without consent, "
        "or a scam, including how the issuer investigated it.",
    ),
    "customer_service": (
        "Customer service",
        "The service experience is the main problem: long holds, rude or unhelpful "
        "staff, conflicting information, no call back, or no way to reach a person. "
        "Use this only when no other theme is the underlying cause.",
    ),
    "credit_limit_account_closure": (
        "Credit limit or account closure",
        "A credit limit decrease or refused increase, an account closed, suspended or "
        "restricted by the issuer, a financial review, an application denial, or "
        "difficulty closing an account.",
    ),
    "billing": (
        "Billing",
        "Payments, interest and non-annual fees: late fees, interest charges, APR "
        "changes, payment posting or autopay problems, statements, balance transfers, "
        "promotional rates, collections and credit bureau reporting of the account.",
    ),
    "other": (
        "Other",
        "Anything that does not fit the themes above, or a narrative too short or "
        "unclear to classify.",
    ),
}

THEME_KEYS: list[str] = list(THEMES)
THEME_LABELS: dict[str, str] = {k: v[0] for k, v in THEMES.items()}

# Themes that make up the "fee, credit and benefit" group used in the event study.
MEMBERSHIP_VALUE_THEMES: set[str] = {
    "annual_fee",
    "statement_credit_benefit",
    "rewards_points",
    "lounge_travel_benefit",
    "insurance_protection_claim",
}

SENTIMENTS: dict[str, str] = {
    "very_negative": "Angry or distressed: alleges deception, theft or discrimination, "
    "describes serious harm, or threatens legal action or leaving.",
    "negative": "Clearly dissatisfied but measured in tone.",
    "neutral_or_mixed": "Mostly factual, asks for help, or mixes praise with a problem.",
}
SENTIMENT_KEYS: list[str] = list(SENTIMENTS)

MAX_NAMED_BENEFITS = 5

# JSON schema for structured output. additionalProperties is false and every field is
# required, which the structured output feature needs.
OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "primary_theme": {"type": "string", "enum": THEME_KEYS},
        "secondary_theme": {"anyOf": [{"type": "string", "enum": THEME_KEYS}, {"type": "null"}]},
        "sentiment": {"type": "string", "enum": SENTIMENT_KEYS},
        "named_benefits": {"type": "array", "items": {"type": "string"}},
        "card_product": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["primary_theme", "secondary_theme", "sentiment", "named_benefits", "card_product"],
    "additionalProperties": False,
}


class TaxonomyError(ValueError):
    """Raised when classifier output cannot be mapped onto the taxonomy."""


@dataclass
class Classification:
    primary_theme: str
    secondary_theme: str | None
    sentiment: str
    named_benefits: list[str] = field(default_factory=list)
    card_product: str | None = None

    @property
    def is_membership_value(self) -> bool:
        return self.primary_theme in MEMBERSHIP_VALUE_THEMES

    def to_dict(self) -> dict:
        return asdict(self)


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_NULLISH = {"", "none", "null", "n/a", "na", "unknown", "not specified", "not stated"}


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


_LABEL_TO_KEY = {_normalize_key(label): key for key, label in THEME_LABELS.items()}


def normalize_theme(value: object) -> str:
    """Map a theme key or display label onto a taxonomy key."""
    if not isinstance(value, str):
        raise TaxonomyError(f"theme must be a string, got {value!r}")
    key = _normalize_key(value)
    if key in THEMES:
        return key
    if key in _LABEL_TO_KEY:
        return _LABEL_TO_KEY[key]
    raise TaxonomyError(f"unknown theme: {value!r}")


def _clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TaxonomyError(f"expected text or null, got {value!r}")
    text = " ".join(value.split())
    return None if text.lower() in _NULLISH else text


def _clean_benefits(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise TaxonomyError(f"named_benefits must be a list, got {value!r}")
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        text = _clean_optional_text(item)
        if text is None or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(text)
    return out[:MAX_NAMED_BENEFITS]


def parse_classification(raw: str | dict) -> Classification:
    """Validate classifier output and return a Classification.

    Accepts a dict or a JSON string (optionally wrapped in prose or a code fence).
    Raises TaxonomyError for anything that does not fit the taxonomy, so a bad
    response is never silently counted as a valid label.
    """
    if isinstance(raw, str):
        match = _JSON_BLOCK.search(raw)
        if not match:
            raise TaxonomyError("no JSON object found in classifier output")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise TaxonomyError(f"invalid JSON: {exc}") from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise TaxonomyError(f"unsupported classifier output type: {type(raw).__name__}")

    if "primary_theme" not in data:
        raise TaxonomyError("missing primary_theme")
    primary = normalize_theme(data["primary_theme"])

    secondary_raw = _clean_optional_text(data.get("secondary_theme"))
    secondary = normalize_theme(secondary_raw) if secondary_raw else None
    if secondary == primary:
        secondary = None

    sentiment = _normalize_key(str(data.get("sentiment", "")))
    if sentiment not in SENTIMENTS:
        raise TaxonomyError(f"unknown sentiment: {data.get('sentiment')!r}")

    return Classification(
        primary_theme=primary,
        secondary_theme=secondary,
        sentiment=sentiment,
        named_benefits=_clean_benefits(data.get("named_benefits")),
        card_product=_clean_optional_text(data.get("card_product")),
    )
