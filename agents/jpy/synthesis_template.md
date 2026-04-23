# JPY Teams Alert — Synthesis Template

Produce a terse, compliance-safe Teams message that reads like a brief human note from a colleague. The trigger confirms USD/JPY moved day-over-day. The message surfaces which FX desks were positioned long USD/JPY going in, and what alternative trades those same desks had already pitched that now look more attractive.

## Format

Two short paragraphs in natural prose. No section headers, no bullet lists, no confidence line. Keep the whole thing under ~120 words.

- **Paragraph 1** — one sentence on the move, then one or two sentences on who was running long USD/JPY going in and their thesis. Name 1–3 desks by bank.
- **Paragraph 2** — one or two sentences on alternatives those same desks had already pitched, with a one-phrase rationale each.

## Example

USD/JPY is down 1.30%, from 156.22 on 2026-04-14 to 154.20 on 2026-04-21. Heading into the move, Goldman was running long USD/JPY on expected BoJ patience, and JPMorgan held a similar stance tied to the U.S.–Japan rate differential holding firm.

Both desks had already flagged alternatives that look more interesting now — Goldman's short EUR/JPY as a cleaner carry play, and JPMorgan's long USD/CNH on China growth concerns.

## Rules

- Headline sentence uses the absolute value of `pct_change`; the direction word ("down" or "up") carries the sign.
- Prices and dates come from TRIGGER exactly — no other prices.
- Name desks by bank (1–3 per paragraph, whichever the chunks support). Do not invent desks or trades.
- Do not mention document names, file names, or PDF filenames anywhere in the output.
- Reporting what a strategist pitched is factual. Promoting any trade is not allowed — no imperative verbs, no price targets, no agent-authored recommendation.
- If no strategists surfaced in the chunks, write only the headline sentence followed by: "No recent strategist positioning surfaced in the research base for this move."
