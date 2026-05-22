---
name: stop-slop
description: Tighten final equity-research prose before submission.
---

# stop-slop

## When to invoke

Use this before `final_answer`. The final memo should read like analyst work:
dense, specific, source-grounded, and written for a reader making an investment
or diligence decision.

## What to cut

### Throat-clearing openers

- "It's worth noting that..."
- "It's important to recognize that..."
- "We should consider that..."
- "Let me walk you through..."
- "First, let's establish that..."

Fix: delete the opener and start with the claim.

### Meta-narration

- "What follows is an analysis of..."
- "In this memo, we will examine..."
- "As outlined above..."
- "As discussed below..."

Fix: delete. The memo's structure is visible.

### Template contrasts

- "Not X, but Y."
- "This is less about A, more about B."
- "What at first appears to be X turns out to be Y."

Fix: use contrast only when it carries the argument.

### Adverb crutches

- "carefully analyze"
- "thoughtfully consider"
- "comprehensively review"
- "meaningfully assess"

Fix: delete the adverb. The verb should do the work.

### Inanimate agency

- "The data suggests..." -> "The figures show..." or "I conclude..."
- "The numbers tell a story of..." -> "The numbers show..."
- "The analysis reveals..." -> "The filing shows..."
- "The picture that emerges..." -> state the conclusion.

Fix: name the source or the analyst action.

### Fog hedging

- "potentially could be somewhat significant"
- "may, in some circumstances, represent a material risk"
- "appears to be consistent with the view that"

Fix: commit, qualify with a specific condition, or cut.

### False specificity

- "A range of factors"
- "Multiple dimensions"
- "A number of considerations"
- "Various metrics"

Fix: name the factors or remove the sentence.

### Pull-quote flourishes

- "That is the story."
- "And that changes everything."
- "This is what it all comes down to."

Fix: close with substance, not emphasis.

### Lecture transitions

- "With that in mind..."
- "Having established that..."
- "Building on the prior point..."

Fix: delete. A paragraph break is enough.

## What to keep

- Direct claims at the front of sentences.
- Exact figures, not rounded adjectives.
- Active voice.
- Short paragraphs.
- Bullets for ranked or enumerable items.
- Inline filing citations.
- Conclusions stated as conclusions.

## Before and after

Before:

"It's worth noting that the AQR figure of 1.13 potentially represents a
somewhat thin cushion relative to the covenant floor. Considering the full
picture, streamline mechanics add additional layers of complexity and may
suggest operational constraints. The picture that emerges is one of elevated
risk across multiple dimensions."

After:

"Reported AQR: 1.13 (Q1 2020 10-Q Item 2 MD&A). Covenant threshold: 1.00x to
1.05x. Cushion: 8-13 bps. Streamline mechanics can move cash into dominion
before a formal covenant breach, so the reported cushion is thin and partly
illusory."

## Lint pass

Before submitting, scan for these phrases and rewrite the sentence if they
appear:

- "It's worth noting"
- "It's important to"
- "potentially"
- "may be"
- "could potentially"
- "tend to"
- "somewhat"
- "various"
- "a range of"
- "multiple factors"
- "on the one hand"
- "on the other hand"
- "what emerges"
- "the picture"
- "in some respects"
- "to some extent"
- "broadly speaking"
