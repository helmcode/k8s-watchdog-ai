import asyncio
import structlog

from src.config import settings
from src.jobs.queue import JobQueue
from src.jobs.processors import process_job

logger = structlog.get_logger()


async def start_worker(queue: JobQueue) -> asyncio.Task:
    """Start the worker task for processing jobs.

    This creates a background asyncio task that continuously polls the
    job queue and processes jobs in a thread pool, keeping the main
    event loop responsive.

    Args:
        queue: JobQueue instance to pull jobs from

    Returns:
        asyncio.Task that can be cancelled during shutdown

    Example:
        worker_task = await start_worker(queue)
        # ... application runs ...
        worker_task.cancel()  # Stop worker during shutdown
    """
    task = asyncio.create_task(_worker_loop(queue))
    logger.info("worker_started", source="worker")
    return task


async def _worker_loop(queue: JobQueue) -> None:
    """Internal worker loop that processes jobs.

    This loop:
    1. Polls the queue for pending jobs every poll_interval seconds
    2. If a job is found, processes it in a thread pool (via asyncio.to_thread)
    3. The thread pool execution keeps the event loop free for HTTP requests
    4. Handles job completion, failures, and retries

    Args:
        queue: JobQueue instance to pull jobs from

    Note:
        This runs indefinitely until the task is cancelled.
        Uses asyncio.to_thread() to prevent blocking the event loop.
    """
    logger.info(
        "worker_loop_started",
        poll_interval=settings.job_poll_interval,
        max_retries=settings.job_max_retries,
        source="worker",
    )

    while True:
        try:
            # Check for next job in queue
            job = await queue.get_next_job()

            if job:
                logger.info(
                    "worker_processing_job",
                    job_id=job.id,
                    job_type=job.type,
                    retry_count=job.retry_count,
                    source="worker",
                )

                # Mark job as processing
                await queue.mark_processing(job.id)

                try:
                    # Execute job in thread pool to avoid blocking event loop
                    # This is the KEY part that solves the health check issue:
                    # - process_job runs in a separate thread
                    # - Event loop remains free to handle /health requests
                    # - Python GIL is released during I/O operations (Claude API, kubectl, etc.)
                    result = await asyncio.to_thread(process_job, job)

                    # Mark job as completed
                    await queue.mark_completed(job.id, result)

                    logger.info(
                        "worker_job_completed",
                        job_id=job.id,
                        job_type=job.type,
                        source="worker",
                    )

                except Exception as job_error:
                    error_msg = f"{type(job_error).__name__}: {str(job_error)}"

                    # Determine if we should retry
                    should_retry = (
                        job.retry_count < settings.job_max_retries
                    )

                    logger.error(
                        "worker_job_failed",
                        job_id=job.id,
                        job_type=job.type,
                        error=error_msg,
                        retry_count=job.retry_count,
                        will_retry=should_retry,
                        source="worker",
                        exc_info=True,
                    )

                    # Mark as failed (with retry if applicable)
                    await queue.mark_failed(
                        job.id, error_msg, retry=should_retry
                    )

            else:
                # No jobs in queue, wait before polling again
                await asyncio.sleep(settings.job_poll_interval)

        except asyncio.CancelledError:
            # Worker is being shut down
            logger.info("worker_shutting_down", source="worker")
            raise

        except Exception as loop_error:
            # Unexpected error in worker loop itself
            # Log but don't crash the worker
            logger.error(
                "worker_loop_error",
                error=str(loop_error),
                error_type=type(loop_error).__name__,
                source="worker",
                exc_info=True,
            )

            # Wait a bit before continuing to avoid tight error loops
            await asyncio.sleep(5)
