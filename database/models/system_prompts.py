from sqlalchemy import String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .base import BaseModel

class SystemPrompt(BaseModel):
    """
    Tracks and stores iterations of the master system prompt to allow for 
    version control, rollbacks, and a UI-based toggle inside the database.
    """
    __tablename__ = 'system_prompts'

    version: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
