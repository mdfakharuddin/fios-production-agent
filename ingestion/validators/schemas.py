from pydantic import BaseModel, Field
from typing import List, Optional

class RawJobData(BaseModel):
    title: str
    description: str
    budget: str
    skills: List[str]
    raw_text: Optional[str] = None

class RawProposalData(BaseModel):
    title: str
    submitted_date: Optional[str] = None
    status: str
    bid_amount: Optional[str] = None
    client_info: Optional[dict] = None
    hiring_activity: Optional[dict] = None
    raw_text: Optional[str] = None

class MessageItem(BaseModel):
    message_id: Optional[str] = None
    sender: str
    role: Optional[str] = "freelancer"
    text: str
    time: Optional[str] = None
    attachments: List[str] = []

class RawConversationData(BaseModel):
    thread_name: str
    room_id: Optional[str] = None
    messages: List[MessageItem]
    sync_status: Optional[str] = "not_synced"
    last_message_id: Optional[str] = None
    last_message_timestamp: Optional[str] = None
    last_message_preview: Optional[str] = None
    message_count_synced: Optional[int] = 0

class IngestionPayload(BaseModel):
    type: str = Field(..., description="Type of data: 'job_details', 'proposals', 'conversation', 'generic_page', or 'stealth_proposal_job_merge'")
    data: dict | List[dict]
    url: str
    timestamp: str
