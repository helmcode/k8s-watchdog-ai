import asyncio
import structlog
from datetime import datetime
from typing import TYPE_CHECKING

from src.config import settings
from src.orchestrator import K8sWatchdogAgent
from src.reporter import SlackReporter
from src.storage import ReportStorage

if TYPE_CHECKING:
    from src.jobs.queue import Job

logger = structlog.get_logger()


def process_job(job: "Job") -> dict:
    """Process a job based on its type.

    This is the main dispatcher that routes jobs to their specific processors.
    Runs synchronously in a thread pool via asyncio.to_thread().

    Args:
        job: Job instance to process

    Returns:
        Result dictionary with processing outcome

    Raises:
        ValueError: If job type is unknown
        Exception: Any exception from the specific processor

    Note:
        This function runs in a ThreadPoolExecutor, not in the main event loop.
        It's safe to call blocking operations here without affecting /health endpoint.
    """
    logger.info(
        "processing_job",
        job_id=job.id,
        job_type=job.type,
        source="processor",
    )

    if job.type == "generate_report":
        return process_report_generation(job)
    else:
        raise ValueError(f"Unknown job type: {job.type}")


def process_report_generation(job: "Job") -> dict:
    """Process a report generation job.

    This function contains all the logic previously in generate_and_send_report(),
    but runs synchronously in a thread pool. This prevents blocking the event loop.

    The function:
    1. Generates the report using Claude AI
    2. Saves it to storage
    3. Sends it to Slack
    4. Returns processing metadata

    Args:
        job: Job instance with report generation request

    Returns:
        Dict with report metadata (status, report_id, generation_time, etc.)

    Raises:
        Exception: Any error during report generation, storage, or sending

    Note:
        - Runs in ThreadPoolExecutor (separate thread)
        - Uses asyncio.run() to execute async operations in the thread's own event loop
        - Event loop in main thread remains free for /health requests
        - I/O operations (Claude API, kubectl, Slack) release GIL automatically
    """
    logger.info(
        "generating_report_in_worker",
        job_id=job.id,
        cluster=settings.cluster_name,
        source="processor",
    )

    start_time = datetime.now()

    try:
        # Create a new event loop for this thread
        # This is necessary because async operations need an event loop,
        # but we're in a thread pool thread without one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Initialize components (these need to be created in the thread)
            agent = K8sWatchdogAgent()
            storage = ReportStorage()

            # Generate report using Claude AI
            # This is the longest operation (~60-70 seconds)
            report_html, metadata = loop.run_until_complete(
                agent.generate_weekly_report()
            )

            generation_time = (datetime.now() - start_time).total_seconds()

            logger.info(
                "report_generated_in_worker",
                job_id=job.id,
                generation_time_seconds=generation_time,
                report_size_kb=len(report_html) / 1024,
                source="processor",
            )

            # Save to storage
            report_id = loop.run_until_complete(
                storage.save_report(report_html)
            )

            logger.info(
                "report_saved_in_worker",
                job_id=job.id,
                report_id=report_id,
                source="processor",
            )

            # Build informative message about data sources
            tools_message = _build_tools_info_message(metadata, generation_time)

            # Send to Slack
            reporter = SlackReporter()
            loop.run_until_complete(
                reporter.send_html_report(
                    html_content=report_html,
                    filename=f"k8s-report-{settings.client_name}-{settings.cluster_name}-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf",
                    message=tools_message,
                )
            )

            logger.info(
                "report_sent_in_worker",
                job_id=job.id,
                source="processor",
            )

            # Cleanup agent resources
            loop.run_until_complete(agent.cleanup())

            return {
                "status": "success",
                "report_id": report_id,
                "generation_time_seconds": generation_time,
                "report_size_kb": len(report_html) / 1024,
            }

        finally:
            # Clean up the event loop
            loop.close()

    except Exception as e:
        logger.error(
            "report_generation_failed_in_worker",
            job_id=job.id,
            error=str(e),
            error_type=type(e).__name__,
            source="processor",
            exc_info=True,
        )
        raise


def _build_tools_info_message(metadata: dict, generation_time: float) -> str:
    """Build informative message about tools used in report generation.

    Args:
        metadata: Report generation metadata
        generation_time: Time taken to generate report (seconds)

    Returns:
        Formatted message string for Slack
    """
    message_parts = [
        "🤖 *Weekly Cluster Health Report*",
        f"⏱️ Generation time: {generation_time:.1f}s",
        f"🔧 Cluster: `{settings.cluster_name}`",
    ]

    if metadata.get("mcp_servers_used"):
        servers = ", ".join(f"`{s}`" for s in metadata["mcp_servers_used"])
        message_parts.append(f"📡 MCP Servers: {servers}")

    if metadata.get("tools_used"):
        tools = ", ".join(f"`{t}`" for t in metadata["tools_used"][:5])
        message_parts.append(f"🛠️ Tools used: {tools}")

    if metadata.get("total_tool_calls"):
        message_parts.append(f"📝 Total tool calls: {metadata['total_tool_calls']}")

    return "\n".join(message_parts)
