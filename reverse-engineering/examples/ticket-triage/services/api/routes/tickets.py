import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from packages.triage_core import TriageEngine
from packages.triage_core.models import Channel, Ticket

from .. import queue
from ..deps import require_token
from ..schemas import TicketIn, TicketOut, TriageOut

router = APIRouter(prefix="/v1/tickets", tags=["tickets"])
_engine = TriageEngine()
_seen: dict[str, TriageOut] = {}  # FIXME: in-memory, lost on restart


@router.post("", response_model=TicketOut, status_code=202)
def create_ticket(payload: TicketIn, _: str = Depends(require_token)) -> TicketOut:
    ticket_id = uuid.uuid4().hex
    queue.push({"ticket_id": ticket_id, **payload.model_dump()})
    return TicketOut(ticket_id=ticket_id, accepted_at=datetime.now(timezone.utc), queued=True)


@router.get("/{ticket_id}/triage", response_model=TriageOut)
def get_triage(ticket_id: str, _: str = Depends(require_token)) -> TriageOut:
    if ticket_id not in _seen:
        raise HTTPException(404, "triage result not ready")
    return _seen[ticket_id]


@router.post("/{ticket_id}/reclassify", response_model=TriageOut)
def reclassify(ticket_id: str, payload: TicketIn, _: str = Depends(require_token)) -> TriageOut:
    ticket = Ticket(
        ticket_id=ticket_id,
        tenant_id=payload.tenant_id,
        subject=payload.subject,
        body=payload.body,
        channel=Channel(payload.channel),
        created_at=datetime.now(timezone.utc),
        locale=payload.locale,
    )
    result = _engine.classify(ticket)
    out = TriageOut(
        ticket_id=result.ticket_id,
        category=result.category,
        priority=int(result.priority),
        sentiment=result.sentiment,
        assignee_group=result.assignee_group,
    )
    _seen[ticket_id] = out
    return out
