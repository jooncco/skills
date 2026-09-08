"""Domain models shared by the API and the worker."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class Priority(enum.IntEnum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class Channel(enum.StrEnum):
    EMAIL = "email"
    CHAT = "chat"
    PHONE = "phone"
    PORTAL = "portal"


@dataclass(slots=True)
class Ticket:
    ticket_id: str
    tenant_id: str
    subject: str
    body: str
    channel: Channel
    created_at: datetime
    locale: str = "ko-KR"
    attachments: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TriageResult:
    ticket_id: str
    category: str
    priority: Priority
    sentiment: float
    assignee_group: str
    rationale: str
