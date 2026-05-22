---
name: extraction-checklist
description: Pre-submit audit ensuring every claim has a sourced figure, arithmetic is visible, and risks are ranked by velocity.
---

# extraction-checklist

## When to invoke

Run this after drafting the memo and before `stop-slop`. This skill audits the memo for quality gaps.

## Checklist

### 1. Figure Sourcing

For every number in the memo, verify:

- [ ] Source named (filing type, company material, or external source)
- [ ] Period or "as of" date stated
- [ ] Unit explicit ($M, %, bps, shares, x ratio)
- [ ] Section/item/note cited (Item 7, Note 12, Exhibit 99.1)

If any are missing, add them or remove the unsourced figure.

### 2. Arithmetic Visibility

For every derived metric, verify the calculation is shown:

- Cushion: reported value - threshold = X
- Coverage: numerator / denominator = X
- Change: (new - old) / old = X%
- Dilution: new shares / (existing + new) = X%
- Runway: cash / burn rate = X months

If you stated a derived number without showing arithmetic, add it.

### 3. Risk Ranking Order

Verify risks are ranked by stress-response velocity:

- Fastest-crystallizing risk listed first (days/weeks)
- Then medium-velocity risks (months)
- Then slow risks (quarters/years)
- Binary/existential risks ranked above gradual compression

If ranking is wrong or missing, fix it and state the ordering criterion explicitly.

### 4. Missing Disclosures

Verify you named at least one conspicuously absent disclosure:

- What specific information is not in the filing?
- Why does its absence matter for the conclusion?
- What would change if it were disclosed?

If no gaps are named, review the filing for what it does NOT say about the key risk.

### 5. Commitment Check

Verify the memo contains:

- [ ] A directional thesis in the first paragraph
- [ ] A committed conclusion in the last paragraph
- [ ] No "more research is needed" or "further analysis warranted" endings
- [ ] No unresolved "may be" or "potentially" hedges on the main conclusion

### 6. Negative-Weight Traps

Scan for these common analytical errors:

- Did you treat a merger or acquisition as primarily beneficial without noting structural risks (CoC triggers, integration costs)?
- Did you count conditional liquidity (undrawn revolvers, untested facilities) as available without stating the conditions?
- Did you rank a slow risk above a faster one?
- Did you conclude the position is "adequate" without substantial qualification?

If any apply, rewrite the relevant section.
