from fastapi import APIRouter

from .. import queue

router = APIRouter(tags=["ops"])


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict:
    return {"status": "ok", "queue_depth": queue.depth()}
