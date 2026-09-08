from datetime import datetime

from pydantic import BaseModel, Field


class TicketIn(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=512)
    body: str
    channel: str = "portal"
    locale: str = "ko-KR"


class TicketOut(BaseModel):
    ticket_id: str
    accepted_at: datetime
    queued: bool


class TriageOut(BaseModel):
    ticket_id: str
    category: str
    priority: int
    sentiment: float
    assignee_group: str
