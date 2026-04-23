"""FX-specific probes for the JPY agent.

Owns the Postgres query shape + mock fallback. Returns domain-free
Observation objects so the threshold skill doesn't know FX exists."""

import logging
import os

from core.models import Observation
from core.tools import postgres

log = logging.getLogger(__name__)

# Two-row mock used when DATABASE_URL is unset — lets the pipeline run
# end-to-end locally without touching the VM DB. Newest first: (date, close).
_MOCK_CLOSES: list[tuple[str, float]] = [
    ("2026-04-20", 159.00),   # t
    ("2026-04-17", 160.75),   # t-1 (Apr 18–19 weekend)
]

_SQL_LATEST_PAIR = """
WITH with_lag AS (
    SELECT
        business_date,
        spot_rate,
        LAG(business_date) OVER (ORDER BY business_date) AS prev_date,
        LAG(spot_rate)     OVER (ORDER BY business_date) AS prev_rate
    FROM fx_spot_rates
    WHERE currency_pair = %s
      AND spot_rate IS NOT NULL
)
SELECT prev_date, prev_rate, business_date, spot_rate
FROM with_lag
WHERE prev_rate IS NOT NULL
ORDER BY business_date DESC
LIMIT 1;
"""


def usdjpy_dod_pct_change() -> list[Observation]:
    """Return one Observation with USD/JPY day-over-day % change in `.value`.

    Sign convention: positive = USD/JPY up (USD-strong / JPY-weak),
                     negative = USD/JPY down (USD-weak / JPY-strong)."""
    if os.environ.get("DATABASE_URL"):
        log.info("probe: source=db")
        rows = postgres.query(_SQL_LATEST_PAIR, ("USDJPY",))
        if not rows:
            log.warning("probe: no paired rows returned for USDJPY")
            return []
        t1_date_raw, t1_close_raw, t_date_raw, t_close_raw = rows[0]
        t1_date = t1_date_raw.isoformat() if hasattr(t1_date_raw, "isoformat") else str(t1_date_raw)
        t_date = t_date_raw.isoformat() if hasattr(t_date_raw, "isoformat") else str(t_date_raw)
        t1_close = float(t1_close_raw)
        t_close = float(t_close_raw)
    else:
        log.info("probe: source=mock (DATABASE_URL not set)")
        t_date, t_close = _MOCK_CLOSES[0]
        t1_date, t1_close = _MOCK_CLOSES[1]

    pct = (t_close - t1_close) / t1_close * 100
    log.info(
        "probe: USDJPY t-1 %s=%.4f  t %s=%.4f  pct=%+.4f%%",
        t1_date, t1_close, t_date, t_close, pct,
    )

    return [
        Observation(
            timestamp=t_date,
            value=round(pct, 4),
            context={
                "pair": "USDJPY",
                "t_close": t_close,
                "t_date": t_date,
                "t1_close": t1_close,
                "t1_date": t1_date,
            },
        )
    ]
