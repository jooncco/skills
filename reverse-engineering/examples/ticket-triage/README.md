# ticket-triage

Support ticket ingestion and triage service. Tickets arrive over HTTP, are
queued, and a worker classifies them (category + priority + sentiment) before
routing to an assignee.

Run locally: `uvicorn services.api.main:app --reload --port 8080`
