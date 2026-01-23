import json
import structlog
from dataclasses import dataclass
from typing import Optional

from src.storage import ReportStorage

logger = structlog.get_logger()


@dataclass
class Job:
    """Represents a job in the queue."""
    id: int
    type: str
    status: str
    payload: Optional[dict] = None
    created_at: Optional[str] = None
    retry_count: int = 0


class JobQueue:
    """Abstract job queue interface.

    This class provides a clean abstraction over the underlying storage
    mechanism (currently SQLite), making it easy to swap to Redis, RabbitMQ,
    or other queue systems in the future by only modifying this file.
    """

    def __init__(self, storage: ReportStorage):
        """Initialize job queue.

        Args:
            storage: ReportStorage instance for database operations
        """
        self.storage = storage
        logger.info("job_queue_initialized", source="queue")

    async def enqueue(self, job_type: str, payload: Optional[dict] = None) -> int:
        """Add a new job to the queue.

        Args:
            job_type: Type of job to process (e.g., 'generate_report')
            payload: Optional dictionary with job-specific data

        Returns:
            Job ID

        Example:
            job_id = await queue.enqueue('generate_report', {'urgent': True})
        """
        payload_str = json.dumps(payload) if payload else None
        job_id = await self.storage.insert_job(job_type, payload_str)

        logger.info(
            "job_enqueued",
            job_id=job_id,
            job_type=job_type,
            source="queue",
        )

        return job_id

    async def get_next_job(self) -> Optional[Job]:
        """Get the next pending job from the queue.

        Returns:
            Job instance or None if no jobs are pending

        Note:
            For Redis migration: Replace with redis.brpop() or similar
        """
        job_data = await self.storage.get_pending_job()

        if not job_data:
            return None

        # Parse payload if exists
        payload = None
        if job_data.get("payload"):
            try:
                payload = json.loads(job_data["payload"])
            except json.JSONDecodeError:
                logger.warning(
                    "invalid_job_payload",
                    job_id=job_data["id"],
                    source="queue",
                )

        job = Job(
            id=job_data["id"],
            type=job_data["type"],
            status=job_data["status"],
            payload=payload,
            created_at=job_data.get("created_at"),
            retry_count=job_data.get("retry_count", 0),
        )

        logger.debug(
            "job_retrieved",
            job_id=job.id,
            job_type=job.type,
            source="queue",
        )

        return job

    async def mark_processing(self, job_id: int) -> None:
        """Mark a job as currently being processed.

        Args:
            job_id: ID of the job to mark as processing
        """
        await self.storage.update_job_status(job_id, "processing")

        logger.info(
            "job_marked_processing",
            job_id=job_id,
            source="queue",
        )

    async def mark_completed(self, job_id: int, result: dict) -> None:
        """Mark a job as successfully completed.

        Args:
            job_id: ID of the completed job
            result: Result data from job processing
        """
        result_str = json.dumps(result)
        await self.storage.update_job_status(
            job_id, "completed", result=result_str
        )

        logger.info(
            "job_completed",
            job_id=job_id,
            source="queue",
        )

    async def mark_failed(
        self, job_id: int, error: str, retry: bool = False
    ) -> None:
        """Mark a job as failed.

        Args:
            job_id: ID of the failed job
            error: Error message describing the failure
            retry: Whether to retry the job (increments retry_count)
        """
        if retry:
            retry_count = await self.storage.increment_job_retry(job_id)
            logger.warning(
                "job_failed_will_retry",
                job_id=job_id,
                error=error,
                retry_count=retry_count,
                source="queue",
            )
        else:
            await self.storage.update_job_status(
                job_id, "failed", error=error
            )
            logger.error(
                "job_failed",
                job_id=job_id,
                error=error,
                source="queue",
            )
