"""Slack integration for sending reports."""

import httpx
import structlog
from typing import Optional
from io import BytesIO
from weasyprint import HTML

from src.config import settings

logger = structlog.get_logger()


class SlackReporter:
    """Send reports to Slack via webhooks and bot API."""
    
    def __init__(self) -> None:
        """Initialize Slack reporter."""
        self.webhook_url = settings.slack_webhook_url
        self.bot_token = settings.slack_bot_token
        self.channel = settings.slack_channel
        
        logger.info(
            "slack_reporter_initialized",
            has_webhook=bool(self.webhook_url),
            has_bot_token=bool(self.bot_token),
        )
    
    async def send_message(self, text: str) -> None:
        """Send a text message to Slack.
        
        Args:
            text: Message text
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                json={"text": text},
                timeout=30.0,
            )
            response.raise_for_status()
            
        logger.info("slack_message_sent", text_length=len(text))
    
    async def send_html_report(
        self,
        html_content: str,
        filename: str = "cluster-health-report.pdf",
        message: Optional[str] = None,
    ) -> None:
        """Send HTML report to Slack as PDF.
        
        Converts HTML to PDF and uploads it.
        If bot token and channel are configured, uploads the PDF file.
        Otherwise, sends a message with a link or summary.
        
        Args:
            html_content: HTML content
            filename: Filename for the attachment (should end in .pdf)
            message: Optional message to accompany the report
        """
        if self.bot_token and self.channel:
            # Convert HTML to PDF
            logger.info("converting_html_to_pdf", html_size=len(html_content))
            pdf_bytes = self._html_to_pdf(html_content)
            logger.info("pdf_generated", pdf_size=len(pdf_bytes))
            
            # Upload PDF file using Slack Bot API
            await self._upload_file_bytes(pdf_bytes, filename, message, "application/pdf")
        else:
            # Fallback: send message only
            summary_message = message or "📊 Weekly Cluster Health Report Generated"
            await self.send_message(
                f"{summary_message}\n\n"
                "⚠️ Note: Configure SLACK_BOT_TOKEN and SLACK_CHANNEL to receive the full PDF report."
            )
    
    def _html_to_pdf(self, html_content: str) -> bytes:
        """Convert HTML to PDF using WeasyPrint.
        
        Args:
            html_content: HTML content string
            
        Returns:
            PDF as bytes
        """
        # Create PDF in memory
        pdf_buffer = BytesIO()
        HTML(string=html_content).write_pdf(pdf_buffer)
        return pdf_buffer.getvalue()
    
    async def _upload_file_bytes(
        self,
        content: bytes,
        filename: str,
        message: Optional[str],
        content_type: str = "application/octet-stream",
    ) -> None:
        """Upload file bytes to Slack using new files v2 API.
        
        Uses the 3-step process:
        1. files.getUploadURLExternal
        2. POST to external URL
        3. files.completeUploadExternal
        
        Args:
            content: File content
            filename: Filename
            message: Optional initial comment
        """
        auth_headers = {
            "Authorization": f"Bearer {self.bot_token}",
        }
        
        file_size = len(content)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 1: Get upload URL (form-urlencoded)
            step1_data = {
                "filename": filename,
                "length": str(file_size),
            }
            
            logger.info("requesting_upload_url", filename=filename, size=file_size)
            
            step1_response = await client.post(
                "https://slack.com/api/files.getUploadURLExternal",
                headers=auth_headers,
                data=step1_data,
            )
            step1_response.raise_for_status()
            step1_result = step1_response.json()
            
            logger.info("step1_response", result=step1_result)
            
            if not step1_result.get("ok"):
                error_msg = step1_result.get('error', 'Unknown error')
                logger.error("slack_api_step1_failed", error=error_msg, response=step1_result)
                raise RuntimeError(f"Slack API error (step 1): {error_msg}")
            
            upload_url = step1_result["upload_url"]
            file_id = step1_result["file_id"]
            
            logger.info("slack_upload_url_obtained", file_id=file_id)
            
            # Step 2: Upload to external URL
            step2_response = await client.post(
                upload_url,
                content=content,
                headers={"Content-Type": content_type},
            )
            step2_response.raise_for_status()
            
            logger.info("slack_file_uploaded_to_external", file_id=file_id, status=step2_response.status_code)
            
            # Step 3: Complete upload and share to channel (form-urlencoded with JSON string)
            import json
            step3_data = {
                "files": json.dumps([
                    {
                        "id": file_id,
                        "title": "Weekly Cluster Health Report",
                    }
                ]),
                "channel_id": self.channel,
            }
            
            if message:
                step3_data["initial_comment"] = message
            
            step3_response = await client.post(
                "https://slack.com/api/files.completeUploadExternal",
                headers=auth_headers,
                data=step3_data,
            )
            step3_response.raise_for_status()
            step3_result = step3_response.json()
            
            logger.info("step3_response", result=step3_result)
            
            if not step3_result.get("ok"):
                error_msg = step3_result.get('error', 'Unknown error')
                logger.error("slack_api_step3_failed", error=error_msg, response=step3_result)
                raise RuntimeError(f"Slack API error (step 3): {error_msg}")
        
        logger.info("slack_file_shared", filename=filename, channel=self.channel, file_id=file_id)
