"""Filter rules: which rows are credit card complaints and which company is which issuer.

Every string here was read from the archive files (see docs/data_profile.md), not assumed.
The same rules are exposed as Python functions (used in tests and small checks) and as
SQL fragments (used at ingest), and tests assert that the two agree.
"""
from __future__ import annotations

# The CFPB renamed the product in 2023. Before the change, credit cards sat inside
# "Credit card or prepaid card" and are separated from prepaid cards by sub-product.
CARD_PRODUCT_CURRENT = "Credit card"
CARD_PRODUCT_LEGACY = "Credit card or prepaid card"
CARD_SUB_PRODUCTS = (
    "General-purpose credit card or charge card",
    "Store credit card",
)

# Exact company strings in the archive -> issuer label used in this project.
COMPANY_TO_ISSUER: dict[str, str] = {
    "AMERICAN EXPRESS COMPANY": "American Express",
    "JPMORGAN CHASE & CO.": "Chase",
    "CAPITAL ONE FINANCIAL CORPORATION": "Capital One",
    "CITIBANK, N.A.": "Citi",
    "BANK OF AMERICA, NATIONAL ASSOCIATION": "Bank of America",
    "DISCOVER BANK": "Discover",
    "SYNCHRONY FINANCIAL": "Synchrony",
}

ISSUERS: list[str] = [
    "American Express",
    "Chase",
    "Capital One",
    "Citi",
    "Bank of America",
    "Discover",
    "Synchrony",
]


def is_card_complaint(product: str | None, sub_product: str | None) -> bool:
    """True if the row is a credit card complaint (general-purpose, charge or store card)."""
    if product == CARD_PRODUCT_CURRENT:
        return True
    return product == CARD_PRODUCT_LEGACY and sub_product in CARD_SUB_PRODUCTS


def map_issuer(company: str | None) -> str | None:
    """Exact-match lookup. Returns None for companies outside the seven issuers."""
    if company is None:
        return None
    return COMPANY_TO_ISSUER.get(company.strip())


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def card_filter_sql(product_col: str = "product", sub_product_col: str = "sub_product") -> str:
    subs = ", ".join(_sql_str(s) for s in CARD_SUB_PRODUCTS)
    return (
        f"({product_col} = {_sql_str(CARD_PRODUCT_CURRENT)} OR "
        f"({product_col} = {_sql_str(CARD_PRODUCT_LEGACY)} AND {sub_product_col} IN ({subs})))"
    )


def issuer_case_sql(company_col: str = "company") -> str:
    whens = " ".join(
        f"WHEN trim({company_col}) = {_sql_str(company)} THEN {_sql_str(issuer)}"
        for company, issuer in COMPANY_TO_ISSUER.items()
    )
    return f"CASE {whens} ELSE NULL END"
