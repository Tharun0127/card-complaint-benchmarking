# Issuer denominators: research notes

Research date: 30 Sep 2026. Companion to `issuer_denominators.csv`.

Every number in the CSV was read from a filing I downloaded from SEC EDGAR (10-K or earnings supplement). Quotes in the CSV are the table row text with `|` standing in for cell borders. Nothing is filled from memory. Where a figure could not be found it is listed in section 4 and left out of the CSV.

## 1. What each issuer's metric includes and excludes

Purchase volume, USD billions, as reported:

| Issuer | Scope label | 2023 | 2024 | 2025 |
|---|---|---|---|---|
| American Express | USCS billed business | 610.8 | 654.8 | 707.5 |
| JPMorgan Chase | Card Services sales volume, excluding commercial card | 1,163.6 | 1,259.3 | 1,354.7 |
| Capital One | Domestic Card purchase volume | 605.7 | 639.3 | 812.2 |
| Citi | Branded Cards credit card spend volume | 497.4 | 516.1 | 538 |
| Citi | Retail Services credit card spend volume | 94.9 | 90.6 | 88 |
| Bank of America | Total credit card purchase volumes | 363.1 | 368.9 | 377.8 |
| Discover | Discover Card Sales Volume | 217.9 | 212.3 | no standalone figure |
| Synchrony | Purchase volume | 185.2 | 182.2 | 182.3 |

### American Express
- Source: FY2025 10-K, Table 9 (USCS Selected Statistical Information).
- Scope: U.S. Consumer Services segment only. The 10-K says USCS "issues a wide range of proprietary consumer cards and provides services to U.S. consumers".
- Excluded: small business and corporate cards. These are in Commercial Services (CS), which "issues a wide range of proprietary corporate and small business cards and provides services to U.S. businesses" and also "select global corporate clients". CS billed business was 541.9 / 526.5 / 516.0 for 2025 / 2024 / 2023 (Table 11).
- Total US billed business in dollars is not disclosed as a single line. USCS plus CS is close but CS contains some non-US corporate volume.
- Billed business definition: "transaction volumes (including cash advances) on payment products issued by American Express". So cash advances are in.
- Charge cards are in. Charge card balances are carried as Card Member receivables (14.2bn at end 2025), separate from Card Member loans (100.2bn). The CSV gives both "Total loans" and "Card Member loans and receivables" rows. Use one, not both.
- Cards-in-force counts cards, not accounts, and includes supplemental cards. Basic cards-in-force (no supplemental cards) was 34.1 / 32.5 / 30.7 million.

### JPMorgan Chase
- Source: FY2025 10-K, CCB Selected metrics, Card Services block. The row label is "Sales volume, excluding commercial card" (in billions).
- Credit card only. Debit is inside a different row, "Debit and credit card sales volume" (1,940.7 for 2025).
- Glossary: "Debit and credit card sales volume: Dollar amount of card member purchases, net of returns."
- Commercial Card is a CIB product for "corporate and public sector clients" and is excluded.
- The filing does not say that small business credit cards are excluded. CCB serves "consumers and small businesses", so I assume small business cards are inside this number. This is an assumption, not a quote.
- "Cards in force" is "the total number of open credit cards, inclusive of primary cardholders and authorized users". It counts cards, including inactive ones.
- Loans: Card Services period-end loans in the CCB balance sheet table.

### Capital One
- Source: FY2025 10-K, Table 8.1 (Domestic Card Business Results); FY2024 10-K for the 2023 period-end loans.
- Glossary: "Purchase volume: Consists of purchase transactions, net of returns, for the period, and excludes cash advance and balance transfer transactions."
- The Credit Card segment "Consists of our domestic consumer card lending, personal loans, domestic small business card lending and international card businesses in the U.K. and Canada." Domestic Card therefore includes small business card. Total Credit Card purchase volume (with UK and Canada) was 828.5 / 654.4 / 620.3.
- Discover: the 10-K states "Our results of operations for the year ended December 31, 2025 reflect the activity of Discover's acquired business operations for the period since the Closing Date." So 2025 Domestic Card purchase volume (812.2) holds legacy Capital One for the full year plus Discover from 18 May 2025 onward. It is not pro forma. 2023 and 2024 hold no Discover volume.
- Period-end Domestic Card loans jumped from 155.6 to 262.4 for the same reason.
- No card account or active account count is disclosed.

### Citi
- Source: FY2025 10-K and FY2024 10-K, U.S. Personal Banking (USPB) section.
- Two separate lines. Branded Cards is "proprietary credit card portfolios (Value, Rewards and Cash), co-branded card portfolios (including Costco and American Airlines) and personal installment loans". Retail Services is "co-brand and private label relationships (including, among others, The Home Depot, Best Buy and Macy's)".
- For a whole-of-Citi US cards denominator, add the two lines: 592.3 (2023), 606.7 (2024), 626 (2025). The sums are my arithmetic.
- Glossary: "Card spend volume: Dollar amount of card customers' gross purchases. Also known as purchase sales." Note the word "gross". Other issuers say net of returns.
- The FY2025 10-K rounds spend to whole billions (538, 88). The 4Q25 supplement gives quarters to one decimal; they sum to 538.4 and 87.8.
- Reporting change: "Effective January 1, 2025, USPB changed its reporting for certain installment lending products that were transferred from Retail Banking to Branded Cards". For loans I used the "Credit cards" sub-line of Branded Cards for 2024 and 2025 so that installment loans stay out.
- From 1Q 2026 Branded Cards and Retail Services sit in a new "U.S. Consumer Cards (USCC)" segment. FY2026 labels will differ.
- Citi also has a small cards book in Wealth (4.9bn loans at end 2025) that is not in these figures.
- No open account count is disclosed. Only new account acquisitions.

### Bank of America
- Source: FY2025 10-K (Consumer Banking key statistics) and FY2024 10-K for 2023.
- Row: "Total credit card" then "Purchase volumes". Footnote: "Includes consumer credit card portfolios in Consumer Banking and GWIM."
- Consumer only. Small business card is carried in the U.S. small business commercial portfolio and is outside this number.
- Debit card purchase volumes are a separate row (594.6bn in 2025) and are not included.
- The 10-K does not define whether purchase volumes are net of returns or whether cash advances are excluded.
- No account count is disclosed. Only "New accounts (in thousands)": 3,531 (2025), 3,820 (2024), 4,275 (2023).

### Discover
- Source: FY2024 10-K, the last standalone annual report.
- "Discover Card Sales Volume" is "Discover card activity related to sales net of returns". The broader "Discover Card Volume" (224.6bn in 2024) adds "balance transfers, cash advances and other activity". I used Sales Volume.
- These are Discover's own proprietary cards. Network volumes (PULSE, Diners, Network Partners) are separate and excluded.
- No account count is disclosed.
- There is no FY2025 figure. Discover merged into Capital One on 18 May 2025.

### Synchrony
- Source: FY2025 10-K, Other Financial and Statistical Data.
- "Purchase volume, or net credit sales, represents the aggregate amount of charges incurred on credit cards or other credit product accounts less returns during the period."
- Whole company. It covers private label cards, Dual Cards and general purpose co-brand cards, and also consumer installment loans and commercial credit products. Credit cards were 92.8% of loan receivables at end 2025. "Consumer Dual Cards and Co-branded cards totaled 34% of our total loan receivables portfolio at December 31, 2025."
- "Active accounts represent credit card or installment loan accounts on which there has been a purchase, payment or outstanding balance in the current month." This is an activity-based account count, which is a different thing from Amex and Chase cards in force.

## 2. Is purchase volume comparable enough for per-volume complaint rates?

Judgment: usable as a rough scale control with clear caveats. Not clean enough to rank the 7 issuers on a single complaints per $bn league table without adjustment.

Reasons it is not like-for-like:

1. Business card treatment differs. Amex USCS and Bank of America are consumer only. Capital One Domestic Card includes small business card. Chase very likely includes small business card (it only excludes commercial card). Small business spend raises the denominator without adding many CFPB complaints, so Chase and Capital One rates will look lower than they should against Amex and Bank of America.
2. Cash advances. Amex billed business includes cash advances. Capital One excludes cash advances and balance transfers. Discover Sales Volume excludes them. Chase, Citi, Bank of America and Synchrony do not say. The effect is small but the definitions are not identical.
3. Gross versus net. Citi defines spend as "gross purchases". Chase, Capital One, Discover and Synchrony are net of returns. Amex and Bank of America do not say.
4. Spend per account differs by an order of magnitude. Amex has charge cards and a premium base with very high spend per card (USCS average basic card member spending of $21,215 in 2025). Synchrony is mostly private label with low spend per account (182bn over about 69 million active accounts is roughly $2,650 per account, my arithmetic). Many complaints are driven by accounts and balances (billing disputes, fees, collections, credit reporting), not by dollars spent. Per-volume rates will flatter Amex and Chase and penalise Synchrony and Citi Retail Services.
5. Capital One 2025 is a blend. It has about 7.5 months of Discover. If CFPB complaints are still filed under the Discover company name after May 2025, numerator and denominator will not match unless you combine them or restrict Capital One to the legacy book.
6. Discover has no 2025 denominator at all.
7. Citi is two businesses. Branded Cards is comparable to the general purpose issuers. Retail Services is comparable to Synchrony. A single Citi rate mixes both.

Suggested handling:

- Report two rates side by side: complaints per $bn purchase volume and complaints per $bn period-end card loans. If the ranking flips between the two, say so.
- Treat Synchrony (and Citi Retail Services, if the CFPB "Store credit card" sub-product lets you split Citi complaints) as a separate private label peer group.
- For 2025, either combine Capital One and Discover complaints against the Capital One Domestic Card denominator for the post-close period, or drop 2025 from the Capital One and Discover comparison and keep 2023 to 2024.
- Accounts are only available for three issuers and mean three different things (Amex cards in force, Chase open cards including authorized users, Synchrony active accounts). I would not use complaints per million accounts across the panel.
- Period-end loans are available for all 7 in 2023 and 2024 and for 6 in 2025. They are the most consistently defined denominator here, but they understate Amex because charge card balances sit in receivables. Use the Amex "loans and receivables" row if you go this way.

## 3. Verified event dates

### Chase Sapphire Reserve refresh (2025)
- Official press release: "The Most Rewarding Cards Are Here: The New Chase Sapphire Reserve and Introducing Chase Sapphire Reserve for Business", dateline "WILMINGTON, DE, June 23, 2025". https://media.chase.com/news/the-most-rewarding-cards-are-here
- First public announcement: 17 June 2025. This date comes from trade press articles published that day (The Points Guy, Doctor of Credit). I did not find a Chase press release dated 17 June. https://thepointsguy.com/news/chase-sapphire-reserve-refresh-2025 and https://www.doctorofcredit.com/?p=239307
- New applicants: 23 June 2025. The Points Guy: "New applicants approved for the card on (or after) June 23 will immediately unlock the new perks". Doctor of Credit: the new card "will go live on June 23, 2025".
- Existing cardholders: 26 October 2025. Chase press release: "Cardmembers who applied prior to June 23, 2025, will experience these new benefits and features starting October 26, 2025." and their "annual fee will be adjusted to $795 on their next anniversary date following October 26, 2025." So the fee change is staggered by each account's anniversary date, starting with anniversaries from 26 October 2025. Doctor of Credit: "Card renewals on October 26th and beyond will get the $795 annual fee."
- Fee: old $550, new $795. The Points Guy: "$795 ... its increase from its previous $550 annual fee". Chase press release: "$795 with a $195 annual fee for authorized user cards". The old $550 figure is from the trade press, not the Chase release.

### American Express Platinum Card refresh
- Confirmed: announced and launched 18 September 2025. Press release "There's Nothing Like Platinum: American Express Unveils Updated U.S. Consumer and Business Platinum Cards, Each with Over $3,500 in Annual Value", dateline New York, September 18, 2025. https://ir.americanexpress.com/news/investor-relations-news/investor-relations-news-details/2025/Theres-Nothing-Like-Platinum-American-Express-Unveils-Updated-U-S--Consumer-and-Business-Platinum-Cards-Each-with-Over-3500-in-Annual-Value/default.aspx
- New fee: "The new annual fee for each of the U.S. Consumer and Business Platinum Cards is $895."
- Old fee: $695. The Amex release does not state the old fee. Source is trade press: "Effective for new cardmembers as of September 18, 2025, the Amex Platinum annual fee is increasing from $695 to $895" https://liveandletsfly.com/amex-platinum-card-refresh-2025/
- New applicants: new fee from 18 September 2025 (same trade press quote).
- Existing consumer Platinum members: new fee "at their next renewal date on or after January 2, 2026" (Amex release). Existing Business Platinum: "at their next renewal date on or after December 2, 2025". Staggered by renewal date, like Chase.
- The WebFetch tool summarised the Amex and Chase pages for me. The quoted fragments above are as returned by that tool. Open the pages and check the wording before citing them in a paper.

### Capital One / Discover
- Closed 18 May 2025.
- Capital One FY2025 10-K: "On May 18, 2025 (the "Closing Date"), Discover Financial Services ("Discover") merged into Capital One and Discover Bank merged into CONA." https://www.sec.gov/Archives/edgar/data/927628/000092762826000024/cof-20251231.htm
- Press release filed as 8-K exhibit 99.1: "Capital One Completes Acquisition of Discover", dateline "MCLEAN, VA, May 18, 2025". https://www.sec.gov/Archives/edgar/data/0000927628/000119312525122059/d934475dex991.htm
- 18 May 2025 was a Sunday. The first business day of the combined company was Monday 19 May 2025. (Day of week is my calendar arithmetic.)

## 4. Not verified or not found

- Discover FY2025 purchase volume: not found. No standalone annual report exists. Capital One does not split out Discover purchase volume in the 10-K tables I read. Search snippets mentioned Discover contributions quoted on Capital One earnings calls (for example 26.5bn in 2Q25), but I did not fetch a primary source for those, so they are not in the CSV.
- Discover standalone 1Q 2025 (from its last 10-Q): not pursued.
- Capital One 2025 on a legacy-only or pro forma basis: not found.
- Card accounts or cards in force for Capital One, Citi, Bank of America and Discover: not disclosed in the filings I read. Citi and Bank of America disclose new accounts only.
- American Express total US billed business in dollars: not found as a reported line. Only segment figures and growth rates.
- Whether Chase "Sales volume, excluding commercial card" includes small business cards: not stated in the 10-K. Treated as included by assumption.
- Whether Bank of America and Amex purchase volumes are net of returns, and whether Bank of America, Chase, Citi and Synchrony exclude cash advances and balance transfers: not stated in the passages I read.
- A Chase-issued announcement dated 17 June 2025: not found. The 17 June date rests on trade press only. Bankrate and NerdWallet pages returned HTTP errors and were not read.
- The old fees ($550 Sapphire Reserve, $695 Platinum) are from trade press, not from the issuers' own releases.
- Citi FY2025 spend volumes to one decimal as a reported full-year figure: not found. The 10-K gives whole billions.
- Synchrony credit-card-only period-end loans for 2023: not extracted (2024 and 2025 are in the CSV).
