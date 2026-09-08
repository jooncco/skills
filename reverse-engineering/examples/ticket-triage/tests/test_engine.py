from datetime import datetime, timezone

from packages.triage_core.models import Channel, Priority, Ticket
from packages.triage_core import TriageEngine


def _ticket(subject: str, body: str = "", tenant: str = "smallco") -> Ticket:
    return Ticket(
        ticket_id="t1",
        tenant_id=tenant,
        subject=subject,
        body=body,
        channel=Channel.PORTAL,
        created_at=datetime.now(timezone.utc),
    )


def test_outage_keyword_sets_high_priority():
    result = TriageEngine().classify(_ticket("service is down"))
    assert result.category == "outage"
    assert result.priority >= Priority.HIGH


def test_unknown_category_falls_back_to_tier1():
    result = TriageEngine().classify(_ticket("hello"))
    assert result.assignee_group == "cx-tier1"
