from sqlalchemy import String, Integer, Float, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from FIOS.database.models.base import BaseModel

class Client(BaseModel):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[Optional[str]] = mapped_column(String(255))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Financial metrics
    total_spent_on_upwork: Mapped[Optional[float]] = mapped_column(Float)
    total_spent_with_you: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Intelligence / Behavioral metrics
    risk_score: Mapped[float] = mapped_column(Float, default=0.0) # 0-10, higher is worse
    is_micromanager: Mapped[bool] = mapped_column(Boolean, default=False)
    historical_negotiation_frequency: Mapped[float] = mapped_column(Float, default=0.0) # 0-1
    personality_tags: Mapped[Optional[str]] = mapped_column(Text) # Comma-separated or JSON string for now
    
    def __repr__(self):
        return f"<Client(id={self.id}, name='{self.name}', risk={self.risk_score})>"
