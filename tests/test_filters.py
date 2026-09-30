"""Filter logic: which rows count as credit card complaints, and issuer mapping."""
import duckdb
import pytest

from filters import (
    COMPANY_TO_ISSUER,
    ISSUERS,
    card_filter_sql,
    is_card_complaint,
    issuer_case_sql,
    map_issuer,
)

ROWS = [
    # (product, sub_product, company, expected_is_card, expected_issuer)
    ("Credit card", "General-purpose credit card or charge card", "AMERICAN EXPRESS COMPANY", True, "American Express"),
    ("Credit card", "Store credit card", "SYNCHRONY FINANCIAL", True, "Synchrony"),
    ("Credit card or prepaid card", "General-purpose credit card or charge card", "JPMORGAN CHASE & CO.", True, "Chase"),
    ("Credit card or prepaid card", "Store credit card", "CITIBANK, N.A.", True, "Citi"),
    ("Credit card or prepaid card", "General-purpose prepaid card", "AMERICAN EXPRESS COMPANY", False, "American Express"),
    ("Credit card or prepaid card", "Gift card", "DISCOVER BANK", False, "Discover"),
    ("Prepaid card", "General-purpose prepaid card", "CAPITAL ONE FINANCIAL CORPORATION", False, "Capital One"),
    ("Debt collection", "Credit card debt", "BANK OF AMERICA, NATIONAL ASSOCIATION", False, "Bank of America"),
    ("Credit card", "General-purpose credit card or charge card", "CITIZENS FINANCIAL GROUP, INC.", True, None),
    ("Credit card", "General-purpose credit card or charge card", "Discovery Auto Sales LLC", True, None),
    ("Credit card", "General-purpose credit card or charge card", "WELLS FARGO & COMPANY", True, None),
    ("Credit card or prepaid card", None, "CITIBANK, N.A.", False, "Citi"),
]


@pytest.mark.parametrize("product, sub_product, company, is_card, issuer", ROWS)
def test_python_rules(product, sub_product, company, is_card, issuer):
    assert is_card_complaint(product, sub_product) is is_card
    assert map_issuer(company) == issuer


def test_sql_rules_match_python_rules():
    con = duckdb.connect()
    con.execute("CREATE TABLE t (product VARCHAR, sub_product VARCHAR, company VARCHAR)")
    con.executemany("INSERT INTO t VALUES (?, ?, ?)", [r[:3] for r in ROWS])
    got = con.execute(
        f"SELECT coalesce({card_filter_sql()}, false), {issuer_case_sql()} FROM t"
    ).fetchall()
    assert got == [(r[3], r[4]) for r in ROWS]


def test_lookalike_company_names_are_not_matched():
    # Substring matching would wrongly pull these in. The mapping is exact on purpose.
    for name in ["CITIZENS FINANCIAL GROUP, INC.", "FIRST CITIZENS BANCSHARES, INC.",
                 "Discovery Auto Sales LLC", "Citizens Debt relief LLC", "american express company"]:
        assert map_issuer(name) is None


def test_mapping_covers_exactly_the_seven_issuers():
    assert sorted(set(COMPANY_TO_ISSUER.values())) == sorted(ISSUERS)
    assert len(ISSUERS) == 7


def test_whitespace_and_missing_company():
    assert map_issuer("  DISCOVER BANK ") == "Discover"
    assert map_issuer(None) is None
