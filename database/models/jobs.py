import enum
from sqlalchemy import String, Float, Enum, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
import uuid

from FIOS.database.models.base import BaseModel

class JobOutcome(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"
    GHOSTED = "ghosted"
    WITHDRAWN = "withdrawn"
    ONGOING = "ongoing"

class BudgetType(str, enum.Enum):
    FIXED = "fixed"
    HOURLY = "hourly"

class Job(BaseModel):
    __tablename__ = "jobs"

    upwork_job_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("clients.id"))
    
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    
    # Budgeting
    budget_type: Mapped[BudgetType] = mapped_column(Enum(BudgetType))
    budget_min: Mapped[Optional[float]] = mapped_column(Float)
    budget_max: Mapped[Optional[float]] = mapped_column(Float)
    
    # Intelligence classification
    category: Mapped[Optional[str]] = mapped_column(String(255))
    skills_required: Mapped[Optional[list]] = mapped_column(JSON)
    industry: Mapped[Optional[str]] = mapped_column(String(255))
    meta_data: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Outcomes for tracking win/loss analysis
    outcome: Mapped[JobOutcome] = mapped_column(Enum(JobOutcome), default=JobOutcome.PENDING)
    
    # Relationships
    client = relationship("Client", backref="jobs")
    proposals = relationship("Proposal", backref="job")

    def __repr__(self):
        return f"<Job(id={self.id}, title='{self.title[:20]}...', outcome={self.outcome})>"
