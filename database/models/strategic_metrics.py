"""
FIOS Strategic Metrics — Persistent storage for cross-thread intelligence.

Stores precomputed win-pattern analytics that get updated incrementally.
"""

from sqlalchemy import String, Float, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from database.models.base import BaseModel


class StrategicMetrics(BaseModel):
    """
    Single-row table that holds the latest computed strategic intelligence.
    Updated incrementally when job outcomes change.
    """
    __tablename__ = "strategic_metrics"

    # ── Overall ─────────────────────────────────────────────────────────
    total_proposals: Mapped[int]     = mapped_column(Integer, default=0)
    total_wins: Mapped[int]          = mapped_column(Integer, default=0)
    total_losses: Mapped[int]        = mapped_column(Integer, default=0)
    win_rate_overall: Mapped[float]  = mapped_column(Float, default=0.0)

    # ── Win Rate Breakdowns (JSON dicts) ────────────────────────────────
    win_rate_by_niche: Mapped[Optional[dict]]   = mapped_column(JSON)   # {niche: {wins, total, rate}}
    win_rate_by_budget_tier: Mapped[Optional[dict]] = mapped_column(JSON)
    win_rate_by_length_bucket: Mapped[Optional[dict]] = mapped_column(JSON)
    win_rate_by_pricing_pct: Mapped[Optional[dict]]  = mapped_column(JSON)

    # ── Top Performers ──────────────────────────────────────────────────
    top_niches: Mapped[Optional[list]]   = mapped_column(JSON)   # [{niche, win_rate, count}]
    underperforming_niches: Mapped[Optional[list]] = mapped_column(JSON)
    optimal_length_range: Mapped[Optional[dict]]   = mapped_column(JSON)  # {min, max, avg_winning}
    optimal_price_range: Mapped[Optional[dict]]    = mapped_column(JSON)  # {min, max, avg_winning}

    # ── Negotiation ─────────────────────────────────────────────────────
    avg_negotiation_discount_pct: Mapped[float] = mapped_column(Float, default=0.0)

    # ── Correlations ────────────────────────────────────────────────────
    correlations: Mapped[Optional[dict]] = mapped_column(JSON)
    # e.g. {client_score_vs_win: 0.65, urgency_vs_speed: 0.42, similarity_vs_win: 0.58}

    # ── AI-generated insights ───────────────────────────────────────────
    insights: Mapped[Optional[list]] = mapped_column(JSON)  # ["Insight 1", "Insight 2"]

    # ── Raw snapshot for debugging ──────────────────────────────────────
    raw_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)

    def __repr__(self):
        return f"<StrategicMetrics(wins={self.total_wins}/{self.total_proposals}, rate={self.win_rate_overall}%)>"
