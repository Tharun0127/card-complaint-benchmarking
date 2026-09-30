"""Prompt for the complaint classifier.

PROMPT_VERSION is part of the cache key. Change it whenever the prompt or the taxonomy
changes, so old labels are never mixed with new ones.
"""
from __future__ import annotations

from taxonomy import SENTIMENTS, THEMES

PROMPT_VERSION = "v1"

# Narratives longer than this are cut, and the cut is marked in the prompt and recorded
# in the cache. It bounds cost on the long tail; the share affected is in the data profile.
MAX_NARRATIVE_CHARS = 6000
TRUNCATION_MARKER = "\n[narrative cut here for length]"


def _theme_block() -> str:
    return "\n".join(f"- {key}: {definition}" for key, (_, definition) in THEMES.items())


def _sentiment_block() -> str:
    return "\n".join(f"- {key}: {definition}" for key, definition in SENTIMENTS.items())


SYSTEM_PROMPT = f"""You label consumer complaints about US credit cards for a card membership analytics team. Each complaint was submitted to the Consumer Financial Protection Bureau. Personal details are redacted as XXXX. The team uses your labels to measure which parts of card membership cause the most friction, so accuracy on the membership themes (annual fee, credits, rewards, travel benefits, protections) matters most.

Read the complaint and return one JSON object with these fields.

primary_theme: the one theme that best describes the underlying problem the customer wants fixed.
{_theme_block()}

How to choose primary_theme:
1. Label the root cause, not the symptom. Nearly every complaint mentions poor service. Use customer_service only when the service experience is itself the problem and no other theme explains it.
2. If the root cause is a membership feature (annual fee, a credit or perk, rewards, a travel benefit, a protection claim), use that theme even when the customer also disputed a charge or asked for a refund.
3. A dispute about a purchase, a merchant, or an unauthorized charge is dispute_fraud, even if interest or fees followed from it.
4. Late fees, interest, payments and credit reporting are billing. The annual fee is never billing.
5. A welcome or sign-up bonus that was not awarded is rewards_points. A statement credit tied to a card benefit is statement_credit_benefit.
6. Use other when nothing fits or the text is too short or unclear to tell. Do not guess.

secondary_theme: a second theme from the same list if the complaint clearly raises another distinct problem, otherwise null. It must differ from primary_theme.

sentiment: the tone of the complaint.
{_sentiment_block()}

named_benefits: a list of specific card benefits, credits or programs the customer names, in short canonical form, for example "airline fee credit", "Uber Cash", "Centurion Lounge", "Priority Pass", "welcome bonus", "companion certificate", "purchase protection", "trip delay insurance", "Membership Rewards", "Ultimate Rewards". Include only benefits the text mentions. Use an empty list when none are named. At most 5 items.

card_product: the card product the customer names, for example "Platinum Card", "Gold Card", "Sapphire Reserve", "Venture X", "Costco Anywhere Visa". Use null when no product is named. Do not infer a product from the issuer or from the benefits.

Examples

Complaint: "My annual fee went from $550 to $795 with no notice I could find. I called to cancel within 30 days and they refused to refund the fee."
{{"primary_theme": "annual_fee", "secondary_theme": null, "sentiment": "negative", "named_benefits": [], "card_product": null}}

Complaint: "I have the Platinum card mostly for the airline credit. I selected XXXX as my airline and bought seat upgrades but the $200 credit never posted. Three reps gave me three different answers."
{{"primary_theme": "statement_credit_benefit", "secondary_theme": "customer_service", "sentiment": "negative", "named_benefits": ["airline fee credit"], "card_product": "Platinum Card"}}

Complaint: "I met the spend requirement for the 80,000 point offer on my Sapphire Preferred and they now say I am not eligible because of a previous card. This is bait and switch and I will be closing every account I have."
{{"primary_theme": "rewards_points", "secondary_theme": null, "sentiment": "very_negative", "named_benefits": ["welcome bonus"], "card_product": "Sapphire Preferred"}}

Complaint: "Someone used my card for $1,900.00 at a store in a state I have never visited. The bank denied my claim twice and keeps charging me interest on it."
{{"primary_theme": "dispute_fraud", "secondary_theme": "billing", "sentiment": "negative", "named_benefits": [], "card_product": null}}

Complaint: "They closed my account without warning after 12 years of on time payments and my score dropped. Please help me understand why."
{{"primary_theme": "credit_limit_account_closure", "secondary_theme": null, "sentiment": "neutral_or_mixed", "named_benefits": [], "card_product": null}}

Complaint: "My flight was delayed 9 hours. I filed under the trip delay coverage on my card and the benefits administrator has asked for the same documents four times over two months."
{{"primary_theme": "insurance_protection_claim", "secondary_theme": null, "sentiment": "negative", "named_benefits": ["trip delay insurance"], "card_product": null}}

Return only the JSON object."""


def build_user_message(narrative: str) -> tuple[str, bool]:
    """Return the user message and whether the narrative was cut for length."""
    text = narrative.strip()
    truncated = len(text) > MAX_NARRATIVE_CHARS
    if truncated:
        text = text[:MAX_NARRATIVE_CHARS] + TRUNCATION_MARKER
    return f"<complaint>\n{text}\n</complaint>", truncated
