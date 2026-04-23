"""Trigger, rule, templates, and feedback vocab for the JPY agent."""

from core.models import Rule
from agents.jpy.probes import usdjpy_dod_pct_change

STALENESS_DAYS = 14
RELEVANCE_THRESHOLD = 1.5

# Signed threshold — the single knob that picks direction AND magnitude:
#   positive  → fire on USD/JPY up   (USD-strong)
#   negative  → fire on USD/JPY down (USD-weak)
# Prod intent: -1.0 (fire on USD-weak ≥1%). Currently lowered for testing.
MATERIALITY_PCT = 0.3

# Probe + rule handed to core.skills.threshold.evaluate.
PROBE = usdjpy_dod_pct_change
RULE = Rule(name="crosses_signed_threshold", params={"threshold": MATERIALITY_PCT})

# Kept for backwards-compat with existing downstream logging.
PRICE_KEY = "USDJPY"

# Controlled vocabulary for feedback tags. Unknown tags warn but are accepted
# (feedback.record) so analysts can surface new patterns without a code change.
FEEDBACK_TAG_VOCAB = [
    "noise",
    "actionable",
    "boj_regime",
    "intervention_risk",
    "yield_driven",
    "risk_off",
    "positioning",
]

# Seed question for the pre-created Bagel chat session (placeholders filled
# from the trigger in run.py).
BAGEL_FOLLOWUP_QUESTION = (
    "What are the latest strategist views and positioning scenarios for {pair} "
    "given the {direction} move of {pct_abs}% on {t_date}?"
)

# TODO (domain): trusted-source priority list for tie-breaking on conflicting chunks.
