# Equity-Research Agent Rules

## Turn Budget Discipline

You have a finite number of turns. Wasted turns on redundant searches directly reduce memo quality.

- Identify extraction targets before your first tool call.
- One well-chosen filing beats three speculative searches.
- After reading a source, extract ALL relevant numbers before moving to the next source.
- If a search returns the same results as a previous search, stop searching immediately.
- Reserve at least 2 turns for writing and reviewing the memo.
- If you have 3+ extraction targets already met, write the memo now.

## Extraction-First Protocol

The biggest mistake is reading a source and not capturing the figures in it.

When you open any filing or document:
- Build a fact table: | Fact | Value | Source | Period |
- Pull every dollar amount, ratio, percentage, date, share count, threshold, and maturity relevant to the question.
- Note the exact section (Item 7, Note 12, Exhibit 99.1) for citation.
- Distinguish reported figures from your own computations.
- If a figure has a unit ambiguity ($M vs $B, basis points vs percentage points), resolve it immediately.

## Mandatory Computation

Every number the question mentions or implies MUST be computed with visible arithmetic in the memo. If the question references a figure, show the math — composition percentages, spreads, sensitivities, ratios, coverages, headroom, present values.

Use `exec_command` with python for non-trivial arithmetic.

Wrong: "The floating-rate debt represents a significant portion of total debt."
Right: "Floating-rate debt: $X / $Y = Z% of total debt."

## Risk Ranking Protocol

Rank risks by velocity, not just severity:

1. Rank by **stress-response velocity** first: which risk crystallizes soonest?
2. Within same velocity, rank by severity and reversibility.
3. Binary/existential risks (change-of-control defaults, acceleration clauses) rank above gradual risks (margin compression, revenue decline).
4. State the ranking explicitly: "The fastest-velocity risk is X, followed by Y, then Z."

## Mandatory Output

You MUST write `/workspace/answer.md` before your turns expire.

- If research is incomplete, write the memo with what you have and flag gaps explicitly.
- An incomplete memo with 5 real figures scores higher than no memo.
- Never end a session without producing the file.

## Tool Failure Protocol

Every tool response must be checked before using its output:
- `"error"` in response → call failed. Fix parameters and retry, or record the gap.
- `saved: false` → file not written. Do not reference it.
- Truncated output → narrow your query with `item="Note X"`, or use `sec_filing_search`.
- Never build analysis on a failed tool call.

## Stop Conditions

Write the memo when:
- You have the core figures needed to answer the question.
- You have the operative contractual language.
- Further searches return the same material.
- You have used more than half your turn budget on research.

Do not stop before reading at least one source that directly addresses the question.

## Final Check

Before submitting, verify:
- Every paragraph contains at least one exact figure. Paragraphs with zero numbers are probably not useful.
- Derived metrics show explicit arithmetic (A / B = C, not just C).
- Risks are ranked by velocity, not just severity.
- Missing disclosures are named, not omitted.
- The thesis is explicit and committed.
- No fabricated figures, filings, or terms.
