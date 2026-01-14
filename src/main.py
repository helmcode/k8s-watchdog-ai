"""Main entry point for K8s Watchdog AI - FastAPI Server."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import settings
from src.orchestrator import K8sWatchdogAgent
from src.reporter import SlackReporter
from src.storage import ReportStorage


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
agent: Optional[K8sWatchdogAgent] = None
report_in_progress = False


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


def _build_tools_info_message(metadata: dict, generation_time: float) -> str:
    """Build informative message about tools used and data sources.
    
    Args:
        metadata: Tools metadata from agent
        generation_time: Report generation time in seconds
        
    Returns:
        Formatted message string
    """
    message_parts = [
        f"📊 *Weekly Health Report - {settings.cluster_name}*",
        f"🕒 Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"⏱️ Generation time: {generation_time:.1f}s",
        "",
        "📦 *Data Sources:*",
    ]
    
    # Kubernetes tools
    k8s_tools = metadata.get("k8s_tools_used", [])
    if k8s_tools:
        message_parts.append(f"✅ Kubernetes API: {len(k8s_tools)} tool types used")
        message_parts.append(f"   • Tools: {', '.join(sorted(set(k8s_tools)))}")
    
    # Prometheus tools - only report as available if actually used
    prom_tools = metadata.get("prom_tools_used", [])
    prom_failed = metadata.get("prom_tools_failed", [])
    
    if prom_tools and not prom_failed:
        message_parts.append(f"✅ Prometheus: {len(prom_tools)} tool types used")
        message_parts.append(f"   • Tools: {', '.join(sorted(set(prom_tools)))}")
        message_parts.append(f"   • Metrics analyzed successfully")
    elif prom_failed:
        message_parts.append(f"❌ Prometheus: Connection failed")
        for failed in prom_failed[:2]:  # Show max 2 errors
            error_msg = failed['error'][:80] + "..." if len(failed['error']) > 80 else failed['error']
            message_parts.append(f"   • {error_msg}")
    elif not prom_tools:
        message_parts.append(f"⚠️ Prometheus: Not available or not used")
        message_parts.append(f"   • Report generated using Kubernetes data only")
    
    # Other failed tools
    other_failed = [f for f in metadata.get("tools_failed", []) if not f["tool"].startswith("prometheus_")]
    if other_failed:
        message_parts.append("")
        message_parts.append("❌ *Other Issues:*")
        for failed in other_failed:
            message_parts.append(f"   • {failed['tool']}: {failed['error'][:60]}")
    
    message_parts.append("")
    message_parts.append(f"📝 Total tool calls: {metadata['total_tool_calls']}")
    
    return "\n".join(message_parts)


async def generate_and_send_report() -> dict:
    """Generate report and send to Slack.
    
    Returns:
        Report metadata dict
    """
    global report_in_progress, storage, agent
    
    if report_in_progress:
        logger.warning("report_generation_already_in_progress")
        return {"status": "skipped", "reason": "already_in_progress"}
    
    report_in_progress = True
    
    try:
        logger.info("generating_weekly_report", cluster=settings.cluster_name)
        start_time = datetime.now()
        
        # Generate report
        report_html, metadata = await agent.generate_weekly_report()
        
        generation_time = (datetime.now() - start_time).total_seconds()
        
        logger.info(
            "report_generated",
            generation_time_seconds=generation_time,
            report_size_kb=len(report_html) / 1024,
        )
        
        # Save to storage
        report_id = await storage.save_report(report_html)
        logger.info("report_saved_to_storage", report_id=report_id)
        
        # Build informative message about data sources
        tools_message = _build_tools_info_message(metadata, generation_time)
        
        # Send to Slack
        reporter = SlackReporter()
        await reporter.send_html_report(
            html_content=report_html,
            filename=f"cluster-health-report-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf",
            message=tools_message,
        )
        logger.info("report_sent_to_slack")
        
        return {
            "status": "success",
            "report_id": report_id,
            "generation_time_seconds": generation_time,
            "report_size_kb": len(report_html) / 1024,
        }
        
    except Exception as e:
        logger.error(
            "report_generation_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
        }
    finally:
        report_in_progress = False
        # Cleanup MCP resources
        if agent:
            await agent.cleanup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global storage, agent
    
    logger.info(
        "k8s_watchdog_ai_starting",
        version="0.1.0",
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
    
    # Initialize agent
    agent = K8sWatchdogAgent()
    logger.info("agent_initialized")
    
    yield
    
    logger.info("k8s_watchdog_ai_shutdown")


# Create FastAPI app
app = FastAPI(
    title="K8s Watchdog AI",
    description="Autonomous Kubernetes cluster observability with AI-powered reports",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        cluster=settings.cluster_name,
    )


@app.post("/report", response_model=ReportResponse)
async def trigger_report(background_tasks: BackgroundTasks):
    """Trigger report generation manually."""
    if report_in_progress:
        raise HTTPException(
            status_code=409,
            detail="Report generation already in progress"
        )
    
    # Run in background
    background_tasks.add_task(generate_and_send_report)
    
    return ReportResponse(
        status="accepted",
        message="Report generation started in background",
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
        "version": "0.1.0",
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
