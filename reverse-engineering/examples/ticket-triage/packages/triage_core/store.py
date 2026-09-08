"""Persistence for tickets and triage results."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class TicketRow(Base):
    __tablename__ = "tickets"
    ticket_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), index=True, nullable=False)
    subject = Column(String(512), nullable=False)
    body = Column(Text, nullable=False)
    channel = Column(String(16), nullable=False)
    created_at = Column(DateTime, nullable=False)


class TriageRow(Base):
    __tablename__ = "triage_results"
    ticket_id = Column(String(64), primary_key=True)
    category = Column(String(32), nullable=False)
    priority = Column(Integer, nullable=False)
    sentiment = Column(Float, nullable=False)
    assignee_group = Column(String(64), nullable=False)


def make_session_factory(db_url: str):
    engine = create_engine(db_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
