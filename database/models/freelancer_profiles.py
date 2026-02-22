from sqlalchemy import String, Text, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from database.models.base import BaseModel

class FreelancerProfile(BaseModel):
    """
    Static Profile Memory.
    Stores the user's Upwork profile details for AI positioning.
    """
    __tablename__ = "freelancer_profiles"

    name: Mapped[str] = mapped_column(String(255))
    title: Mapped[Optional[str]] = mapped_column(String(500))
    overview: Mapped[Optional[str]] = mapped_column(Text)
    skills: Mapped[Optional[list]] = mapped_column(JSON)
    hourly_rate: Mapped[Optional[float]] = mapped_column(Float)
    niches: Mapped[Optional[list]] = mapped_column(JSON) # e.g. ["Restaurant Menus", "SaaS UX"]
    style_guide: Mapped[Optional[str]] = mapped_column(Text) # Authority style, tone, etc.

    def __repr__(self):
        return f"<FreelancerProfile(name='{self.name}', title='{self.title}')>"
