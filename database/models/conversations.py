from sqlalchemy import String, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
import uuid

from database.models.base import BaseModel

class Conversation(BaseModel):
    __tablename__ = "conversations"

    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("jobs.id"))
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("clients.id"))
    
    thread_name: Mapped[str] = mapped_column(String(255))
    room_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    
    # Sync Metadata
    last_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    last_message_timestamp: Mapped[Optional[str]] = mapped_column(String(255))
    last_message_preview: Mapped[Optional[str]] = mapped_column(Text)
    sync_status: Mapped[str] = mapped_column(String(50), default="not_synced")
    message_count_synced: Mapped[int] = mapped_column(default=0)

    # Store the actual messages. 
    # For a complex system, this might be a separate Message table, 
    # but for an AI memory block, storing the thread as JSON is often faster to pass to LLMs
    messages_json: Mapped[list] = mapped_column(JSON, default=list) 
    
    summary: Mapped[Optional[str]] = mapped_column(Text)
    
    # Phase 1: CRM & Intelligence Fields
    analytics: Mapped[dict] = mapped_column(JSON, default=dict)
    action_items: Mapped[list] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    
    # Phase 2: CRM Dashboard Fields
    tags: Mapped[list] = mapped_column(JSON, default=list)
    revenue_tracking: Mapped[dict] = mapped_column(JSON, default=dict)
    follow_up_at: Mapped[Optional[str]] = mapped_column(String(50))   # ISO datetime string
    notes: Mapped[Optional[str]] = mapped_column(Text)                 # Quick CRM note

    # Relationships
    job = relationship("Job", backref="conversations")
    client = relationship("Client", backref="conversations")

    def __repr__(self):
        return f"<Conversation(id={self.id}, thread='{self.thread_name}')>"
