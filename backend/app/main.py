"""Application entrypoint."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitMiddleware
from app.db.database import SessionLocal, init_db
from app.mcp.server import mcp_router
from app.services.ingestion_job_service import IngestionJobService

logger = logging.getLogger(__name__)
settings = get_settings()
configure_logging(settings.debug)

_POLL_SECONDS = float(os.getenv("INGESTION_WORKER_POLL_SECONDS", "2"))


async def _ingestion_worker_loop() -> None:
    """Process queued ingestion jobs in a background asyncio task.

    Runs the blocking DB operations in a thread-pool executor so the event
    loop stays free.  One job is claimed-and-processed per iteration; when the
    queue is empty the loop sleeps for _POLL_SECONDS before trying again.
    """
    service = IngestionJobService()
    loop = asyncio.get_running_loop()
    logger.info("In-process ingestion worker started (poll=%.1fs)", _POLL_SECONDS)

    def _process_one() -> bool:
        with SessionLocal() as db:
            return service.process_next(db)

    while True:
        try:
            processed = await loop.run_in_executor(None, _process_one)
            if not processed:
                await asyncio.sleep(_POLL_SECONDS)
        except asyncio.CancelledError:
            logger.info("In-process ingestion worker shutting down")
            return
        except Exception:
            logger.exception("Ingestion worker iteration failed; will retry")
            await asyncio.sleep(_POLL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker_task = asyncio.create_task(_ingestion_worker_loop(), name="ingestion-worker")
    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(mcp_router)
app.add_middleware(RateLimitMiddleware)
