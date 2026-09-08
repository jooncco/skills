from fastapi import FastAPI

from .routes import health, tickets

app = FastAPI(title="ticket-triage", version="0.4.2")
app.include_router(tickets.router)
app.include_router(health.router)
