---
name: financial-claim-grounding
description: Rules for verifying quantitative financial claims and avoiding fabricated figures.
---

# financial-claim-grounding

## When to invoke

Use this before writing any quantitative claim: dollar amounts, ratios, percentages, maturities, thresholds, share counts, tranche sizes, compensation figures, segment metrics, or growth rates.

## Core Rules

### Every Number Needs a Source

For each figure:

1. You read it from a source or computed it from sourced inputs.
2. You know the period or measurement date.
3. You know the unit.
4. You can cite the filing, company material, or external source.

If any of those are missing, do not present the number as fact.

### Computed Metrics Need Visible Arithmetic

Show the arithmetic for:

- Liquidity runway
- Covenant cushion
- Unused authorization
- YoY or QoQ changes
- Debt / EBITDA
- Coverage ratios
- Dilution percentages
- Segment mix
- Gross-to-net reconciliations

Example:

"Unused authorization: $1,295.8M remaining / $1,500.0M authorization = 86.4% unused."

### Distinguish Reported From Derived

Reported:

"Reported AQR was 1.13 as of March 31, 2020."

Derived:

"Cushion to the 1.05 upper threshold was 8 bps: 1.13 - 1.05 = 0.08."

Do not blend the two. Readers need to know which numbers came directly from the filing and which are analyst calculations.

### Unit Discipline

- $M and $B are not interchangeable.
- Basis points are not percentage points.
- LTM, TTM, fiscal year, calendar year, quarter-to-date, and point-in-time balances are different.
- Gross and net share counts are different.
- Authorization, availability, draw, use, and remaining capacity are different.
- Fair value, carrying value, principal, proceeds, and notional exposure are different.

Label the unit every time ambiguity is possible.

### Date-Stamp Balance Sheet and Contract Claims

Use "as of" for balances, covenants, share counts, authorizations, maturities, and liquidity.

Use "for the period ended" for revenue, expense, EBITDA, cash flow, and segment contribution.

Use filing date for 8-K events and proxy filing date for governance or compensation materials.

## Common Unsupported Claims

| Claim Type | Weak Version | Strong Version |
|---|---|---|
| Liquidity | "Liquidity was tight." | "Cash was $32.4M and revolver availability was $40.0M as of March 31, 2020, but availability depended on covenant compliance." |
| Covenant | "The company had a covenant issue." | "AQR was 1.13 versus a 1.00-1.05 threshold range, leaving 8-13 bps of cushion." |
| Dilution | "Warrants could dilute holders." | "Warrant dilution cannot be quantified without the strike price and settlement terms." |
| Segment trend | "The segment weakened." | "Segment revenue fell from $X to $Y, a Z% decline, under the current segment definition." |
| Non-GAAP | "Adjusted EBITDA improved." | "Company-defined Adjusted EBITDA was $X, reconciled from GAAP net income in the 8-K Exhibit 99.1 table." |

## If the Source Is Silent

Do not fill the gap with a plausible number. State the gap and explain its consequence.

Useful language:

- "The filing discloses aggregate debt maturity but not weighted-average coupon by tranche."
- "The proxy discloses grant-date fair value but not realized value."
- "The 10-Q discloses the facility size but not whether a waiver had been obtained."
- "The company does not disclose the warrant strike price, so dilution timing cannot be quantified."

## Final Check

For every number in the memo, ask:

1. Where did it come from?
2. What period does it cover?
3. What unit is it in?
4. Is it reported or computed?
5. Would the conclusion change if the number were wrong?

If the answer to any of the first four is unclear, remove or re-source the claim.
