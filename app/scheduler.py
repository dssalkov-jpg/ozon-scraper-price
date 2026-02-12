import os
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import Run, RegionProfile
from .worker import run_collect

logger = logging.getLogger(__name__)

MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "1"))
scheduler = BackgroundScheduler(timezone="UTC")


def can_start(db: Session) -> bool:
    running = db.query(Run).filter(Run.status == "running").count()
    return running < MAX_CONCURRENT_RUNS


def start_run(region_profile_id: int) -> int:
    db = SessionLocal()
    try:
        if not can_start(db):
            raise RuntimeError("run_already_in_progress")

        region = db.query(RegionProfile).filter(RegionProfile.id == region_profile_id).first()
        if not region:
            raise RuntimeError("region_not_found")

        run = Run(
            region_profile_id=region_profile_id,
            status="running",
            started_at=datetime.utcnow()
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            run_collect(db, run.id, region.storage_path)
            run.status = "done"
            run.finished_at = datetime.utcnow()
        except Exception as e:
            logger.error(f"Run failed: {e}")
            run.status = "failed"
            run.error = str(e)[:500]
            run.finished_at = datetime.utcnow()

        db.commit()
        return run.id
    finally:
        db.close()


def schedule_daily():
    hour = int(os.getenv("SCHEDULE_HOUR_UTC", "1"))
    minute = int(os.getenv("SCHEDULE_MINUTE_UTC", "0"))

    def job():
        db = SessionLocal()
        try:
            region = db.query(RegionProfile).order_by(RegionProfile.id.asc()).first()
            if not region:
                logger.warning("No region profiles configured, skipping scheduled run")
                return
            if not can_start(db):
                logger.warning("Run already in progress, skipping scheduled run")
                return
            logger.info(f"Starting scheduled run for region: {region.name}")
            start_run(region.id)
        except Exception as e:
            logger.error(f"Scheduled job failed: {e}")
        finally:
            db.close()

    scheduler.add_job(
        job, "cron",
        hour=hour, minute=minute,
        id="daily_run",
        replace_existing=True
    )
    logger.info(f"Scheduled daily run at {hour:02d}:{minute:02d} UTC")
