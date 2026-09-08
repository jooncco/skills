"""Queue consumer: pops tickets, triages them, persists, then notifies."""
from __future__ import annotations

import logging
import os
import signal
from datetime import datetime, timezone

from packages.triage_core import TriageEngine
from packages.triage_core.models import Channel, Ticket
from packages.triage_core.store import TriageRow, make_session_factory
from services.api import queue
from services.api.config import settings

from .notifier import Notifier

log = logging.getLogger("worker")
_running = True


def _stop(*_args) -> None:
    global _running
    _running = False


def run() -> None:
    signal.signal(signal.SIGTERM, _stop)
    session_factory = make_session_factory(settings.db_url)
    engine = TriageEngine()
    notifier = Notifier(slack_webhook=os.getenv("SLACK_WEBHOOK", ""))

    while _running:
        item = queue.pop()
        if item is None:
            continue
        ticket = Ticket(
            ticket_id=item["ticket_id"],
            tenant_id=item["tenant_id"],
            subject=item["subject"],
            body=item["body"],
            channel=Channel(item.get("channel", "portal")),
            created_at=datetime.now(timezone.utc),
        )
        result = engine.classify(ticket)
        with session_factory() as session:
            session.merge(
                TriageRow(
                    ticket_id=result.ticket_id,
                    category=result.category,
                    priority=int(result.priority),
                    sentiment=result.sentiment,
                    assignee_group=result.assignee_group,
                )
            )
            session.commit()
        notifier.notify({"ticket_id": result.ticket_id, "group": result.assignee_group})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
