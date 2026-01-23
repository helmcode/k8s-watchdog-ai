from contextlib import asynccontextmanager
from typing import Optional
import asyncio

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src import __version__
from src.config import settings
from src.storage import ReportStorage
from src.jobs import JobQueue, start_worker


# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(structlog.stdlib.logging, settings.log_level.upper())
    ),
)

logger = structlog.get_logger()

# Global instances
storage: Optional[ReportStorage] = None
job_queue: Optional[JobQueue] = None
worker_task = None


class ReportResponse(BaseModel):
    """Response model for report generation."""
    status: str
    message: str
    report_id: Optional[int] = None
    generation_time_seconds: Optional[float] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    cluster: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global storage, job_queue, worker_task

    logger.info(
        "k8s_watchdog_ai_starting",
        version=__version__,
        cluster=settings.cluster_name,
        language=settings.report_language,
    )

    # Initialize storage
    storage = ReportStorage()
    await storage.initialize()
    logger.info("storage_initialized")

    # Clean up old reports
    deleted = await storage.cleanup_old_reports()
    logger.info("old_reports_cleaned", count=deleted)

    # Initialize job queue
    job_queue = JobQueue(storage)
    logger.info("job_queue_initialized")

    # Start worker task
    worker_task = await start_worker(job_queue)
    logger.info("worker_task_started")

    yield

    # Shutdown: stop worker gracefully
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    logger.info("k8s_watchdog_ai_shutdown")


# Create FastAPI app
app = FastAPI(
    title="K8s Watchdog AI",
    description="Autonomous Kubernetes cluster observability with AI-powered reports",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint.

    This endpoint remains responsive even during report generation because
    the worker processes jobs in a thread pool, keeping the event loop free.
    """
    return HealthResponse(
        status="healthy",
        version=__version__,
        cluster=settings.cluster_name,
    )


@app.post("/report", response_model=ReportResponse)
async def trigger_report():
    """Trigger report generation by enqueuing a job.

    This endpoint adds a report generation job to the queue and returns immediately.
    The worker task processes the job asynchronously, keeping the event loop free
    for handling health checks and other requests.
    """
    if not job_queue:
        raise HTTPException(
            status_code=503,
            detail="Job queue not initialized"
        )

    # Enqueue job (returns immediately)
    job_id = await job_queue.enqueue("generate_report")

    logger.info(
        "report_job_enqueued",
        job_id=job_id,
        cluster=settings.cluster_name,
    )

    return ReportResponse(
        status="accepted",
        message=f"Report generation job enqueued (job_id={job_id}). Worker will process it.",
    )


@app.get("/reports")
async def list_reports(limit: int = 10):
    """List recent reports."""
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not initialized")

    stats = await storage.get_report_stats()

    return {
        "cluster": settings.cluster_name,
        "statistics": stats,
        "message": "Use report ID to retrieve specific reports from storage",
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "K8s Watchdog AI",
        "version": __version__,
        "cluster": settings.cluster_name,
        "endpoints": {
            "health": "/health",
            "trigger_report": "POST /report",
            "list_reports": "/reports",
            "docs": "/docs",
        }
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
