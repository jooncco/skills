"""Triage engine.

TODO(2025-08): this module has grown into a god object - classification,
sentiment, routing, and the LLM fallback all live here. Split before adding
the multilingual path.
"""
from __future__ import annotations

import logging
import re

from .models import Priority, Ticket, TriageResult
from .rules import (
    CATEGORY_KEYWORDS,
    ESCALATION_TENANTS,
    GROUP_BY_CATEGORY,
    PRIORITY_FLOOR,
)

log = logging.getLogger(__name__)

_NEGATIVE = re.compile(r"(terrible|awful|angry|화가|최악|환불해)", re.I)
_POSITIVE = re.compile(r"(thanks|great|감사|좋아)", re.I)


class TriageEngine:
    """Classifies a ticket and decides who owns it."""

    def __init__(self, llm_client=None, max_body_chars: int = 4000) -> None:
        self._llm = llm_client
        self._max_body = max_body_chars

    def classify(self, ticket: Ticket) -> TriageResult:
        text = f"{ticket.subject}\n{ticket.body}"[: self._max_body].lower()
        category = self._category(text)
        sentiment = self._sentiment(text)
        priority = self._priority(category, sentiment, ticket)
        return TriageResult(
            ticket_id=ticket.ticket_id,
            category=category,
            priority=priority,
            sentiment=sentiment,
            assignee_group=GROUP_BY_CATEGORY.get(category, "cx-tier1"),
            rationale=f"keyword match on '{category}', sentiment {sentiment:+.2f}",
        )

    def _category(self, text: str) -> str:
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(k in text for k in keywords):
                return category
        if self._llm is not None:
            # FIXME: unbounded call, no timeout and no retry budget
            return self._llm.classify(text)
        return "unknown"

    def _sentiment(self, text: str) -> float:
        score = 0.0
        score -= 0.6 * len(_NEGATIVE.findall(text))
        score += 0.4 * len(_POSITIVE.findall(text))
        return max(-1.0, min(1.0, score))

    def _priority(self, category: str, sentiment: float, ticket: Ticket) -> Priority:
        priority = PRIORITY_FLOOR.get(category, Priority.LOW)
        if ticket.tenant_id in ESCALATION_TENANTS:
            priority = Priority(min(int(Priority.URGENT), int(priority) + 1))
        if sentiment <= -1.0:
            priority = Priority.URGENT
        return priority
