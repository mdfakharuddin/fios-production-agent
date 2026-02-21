from sqlalchemy import String, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from FIOS.database.models.base import BaseModel

class Analytics(BaseModel):
    __tablename__ = "analytics_metrics"

    # Dimensions
    time_frame: Mapped[str] = mapped_column(String(50)) # e.g. "weekly", "monthly", "all_time"
    category_or_niche: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Metrics
    total_proposals_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_jobs_won: Mapped[int] = mapped_column(Integer, default=0)
    win_rate_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    
    total_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    total_connects_spent: Mapped[int] = mapped_column(Integer, default=0)
    
    # ROI
    revenue_per_connect: Mapped[float] = mapped_column(Float, default=0.0)

    def __repr__(self):
        return f"<Analytics(time_frame='{self.time_frame}', win_rate={self.win_rate_percentage}%)>"
