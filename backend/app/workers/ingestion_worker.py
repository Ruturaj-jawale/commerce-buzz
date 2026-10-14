"""Run durable commerce-ingestion jobs outside the HTTP API process."""

import logging
import os
import time

from app.db.database import SessionLocal, init_db
from app.services.ingestion_job_service import IngestionJobService


def main() -> None:
    interval_seconds = float(os.getenv("INGESTION_WORKER_POLL_SECONDS", "2"))
    init_db()
    service = IngestionJobService()
    logging.basicConfig(level=logging.INFO)
    logging.info("Ingestion worker started")
    while True:
        db = SessionLocal()
        try:
            processed = service.process_next(db)
        except Exception:
            logging.exception("Ingestion worker loop failed")
            processed = False
        finally:
            db.close()
        if not processed:
            time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
