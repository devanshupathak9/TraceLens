"""Token prices, and the cost of a call derived from them.

The one place prices live. `inference_logs` stores token counts, never money —
prices change, and a stored cost would freeze the rate at write time and go
stale silently. Cost is therefore computed at read time, in `DashboardService`.

Prices are USD per 1M tokens, taken from the vendors' own pricing pages and
last checked on 2026-07-27:
  - https://developers.openai.com/api/docs/pricing
  - https://platform.claude.com/docs/en/about-claude/pricing

Two things to watch when updating:
  - Claude Sonnet 5 is on introductory pricing ($2/$10) through 2026-08-31;
    from 2026-09-01 it becomes $3/$15.
  - Anything not listed here is reported as unpriced (cost `None`) rather than
    as $0, so a new model shows up as "unknown" instead of quietly free.
"""

# model prefix -> (input $/1M tokens, output $/1M tokens)
PRICES: dict[str, tuple[float, float]] = {
    # --- OpenAI ---------------------------------------------------------
    "gpt-5.6-sol": (5.00, 30.00),
    "gpt-5.6-terra": (2.50, 15.00),
    "gpt-5.6-luna": (1.00, 6.00),
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (2.50, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    # --- Anthropic ------------------------------------------------------
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-opus-4-1": (15.00, 75.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-3-5": (0.80, 4.00),
}


def price_for(model: str) -> tuple[float, float] | None:
    """Prices for a model, or None if it isn't in the table.

    Matches on the longest prefix so dated snapshots resolve to their family —
    `gpt-4o-2024-08-06` to `gpt-4o`, `claude-opus-4-5-20251101` to
    `claude-opus-4-5` — and the longest-first rule keeps `gpt-4o-mini` from
    being swallowed by `gpt-4o`.
    """
    name = model.lower()
    match: str | None = None
    for prefix in PRICES:
        if name.startswith(prefix) and (match is None or len(prefix) > len(match)):
            match = prefix
    return PRICES[match] if match else None


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """USD for one model's usage, or None when the model has no price on file."""
    price = price_for(model)
    if price is None:
        return None

    input_price, output_price = price
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
