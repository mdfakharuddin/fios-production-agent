import enum
from sqlalchemy import String, Float, Enum, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
import uuid

from database.models.base import BaseModel

class ProposalStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    INTERVIEWING = "interviewing"
    HIRED = "hired"
    ARCHIVED = "archived"

class Proposal(BaseModel):
    __tablename__ = "proposals"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"))
    
    # The actual data
    cover_letter: Mapped[str] = mapped_column(Text)
    bid_amount: Mapped[float] = mapped_column(Float)
    connects_spent: Mapped[Optional[int]] = mapped_column(Float)
    
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus), default=ProposalStatus.DRAFT)
    
    # Intelligence Data
    # Useful for analytics to see if short/long/funny/serious ones win more
    tone: Mapped[Optional[str]] = mapped_column(String(100))
    length_words: Mapped[Optional[int]] = mapped_column(Float) 

    def __repr__(self):
        return f"<Proposal(id={self.id}, job_id={self.job_id}, status={self.status})>"
