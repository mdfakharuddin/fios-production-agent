from sqlalchemy import String, ForeignKey, Text, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
import uuid
from datetime import datetime

from database.models.base import BaseModel

class Message(BaseModel):
    """
    Normalized message table for granular semantic search and analysis.
    Scenario 1 & 2 from the Strategic Advisor spec.
    """
    __tablename__ = "messages"

    room_id: Mapped[str] = mapped_column(String(255), ForeignKey("conversations.room_id"), index=True)
    
    # role: 'client' | 'freelancer' | 'system'
    role: Mapped[str] = mapped_column(String(50))
    
    content: Mapped[str] = mapped_column(Text)
    
    # Upwork's internal message ID if available
    external_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationship back to conversation
    conversation = relationship("Conversation", backref="messages_list")

    def __repr__(self):
        return f"<Message(role={self.role}, room={self.room_id}, snippet='{self.content[:30]}...')>"
