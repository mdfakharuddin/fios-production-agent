from sqlalchemy import String, Float, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
import uuid

from database.models.base import BaseModel


class PricingHistory(BaseModel):
    """
    Long-term pricing intelligence. 
    Every time we win or lose a proposal, we record what was charged,
    what the job was, and what the outcome was.
    This powers the Scenario 5 pricing advisor.
    """
    __tablename__ = "pricing_history"

    # Job context
    job_title: Mapped[str] = mapped_column(String(500))
    job_category: Mapped[Optional[str]] = mapped_column(String(255))
    job_description_snippet: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[list]] = mapped_column(JSON)  # e.g. ["2 page menu", "restaurant"]

    # Pricing
    amount_charged: Mapped[float] = mapped_column(Float)
    budget_type: Mapped[str] = mapped_column(String(10), default="fixed")  # "fixed" | "hourly"
    competing_bids_count: Mapped[Optional[int]] = mapped_column(Float)

    # Outcome
    outcome: Mapped[str] = mapped_column(String(20), default="unknown")  # won | lost | ghosted | hired
    client_location: Mapped[Optional[str]] = mapped_column(String(100))

    # Source linkage
    proposal_link: Mapped[Optional[str]] = mapped_column(String(500))
    room_id: Mapped[Optional[str]] = mapped_column(String(255))

    def __repr__(self):
        return f"<PricingHistory(title='{self.job_title[:30]}', amount={self.amount_charged}, outcome={self.outcome})>"
