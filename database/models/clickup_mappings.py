from typing import Optional
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid
from database.models.base import BaseModel

class ClickUpMapping(BaseModel):
    """
    Maps Upwork Job/Conversation to ClickUp Task/List.
    Allows for bidirectional synchronization.
    """
    __tablename__ = "clickup_mappings"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    
    clickup_task_id: Mapped[str] = mapped_column(String(255), index=True)
    clickup_list_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Track the last sync hash to prevent loops
    last_sync_hash: Mapped[Optional[str]] = mapped_column(String(500))

    # Relationships
    job = relationship("Job")
    conversation = relationship("Conversation")

    def __repr__(self):
        return f"<ClickUpMapping(job_id={self.job_id}, task_id='{self.clickup_task_id}')>"
