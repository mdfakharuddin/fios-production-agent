from enum import Enum
from pydantic import BaseModel
from typing import Dict, Any

class EventType(str, Enum):
    NEW_JOB_UPLOADED = "new_job_uploaded"
    CONVERSATION_UPDATED = "conversation_updated"
    JOB_OUTCOME_UPDATED = "job_outcome_updated"

class EventPayload(BaseModel):
    event_type: EventType
    data: Dict[str, Any]

class EventTriggerSystem:
    """Basic Even Trigger mechanism to avoid chaos."""
    def __init__(self):
        self.handlers = {}

    def register_handler(self, event_type: EventType, handler_func):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler_func)

    async def trigger(self, event: EventPayload):
        handlers = self.handlers.get(event.event_type, [])
        for handler in handlers:
            # Execute handlers asynchronously
            # Real implementation would likely push to a queue (like Redis or RabbitMQ)
            await handler(event.data)

# Global Instance
triggers = EventTriggerSystem()
