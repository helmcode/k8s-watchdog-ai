import aiosqlite
import structlog
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config import settings

logger = structlog.get_logger()


class ReportStorage:
    """Manages report storage in SQLite database."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize report storage.

        Args:
            db_path: Path to SQLite database file. Uses settings if not provided.
        """
        self.db_path = db_path or settings.sqlite_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info("report_storage_initialized", db_path=self.db_path)

    async def initialize(self) -> None:
        """Initialize database schema."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_name TEXT NOT NULL,
                    generated_at TIMESTAMP NOT NULL,
                    report_html TEXT NOT NULL,
                    report_size INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_cluster_generated 
                ON reports(cluster_name, generated_at DESC)
            """)

            await db.commit()

        logger.info("database_initialized")

    async def save_report(self, html_content: str) -> int:
        """Save a generated report.

        Args:
            html_content: HTML report content

        Returns:
            Report ID
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO reports (cluster_name, generated_at, report_html, report_size)
                VALUES (?, ?, ?, ?)
                """,
                (
                    settings.cluster_name,
                    datetime.now().isoformat(),
                    html_content,
                    len(html_content),
                ),
            )
            await db.commit()
            report_id = cursor.lastrowid

        logger.info(
            "report_saved",
            report_id=report_id,
            size=len(html_content),
            cluster=settings.cluster_name,
        )

        return report_id

    async def get_latest_report(self) -> Optional[dict]:
        """Get the most recent report for the cluster.

        Returns:
            Report dict or None if no reports exist
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, cluster_name, generated_at, report_html, report_size, created_at
                FROM reports
                WHERE cluster_name = ?
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (settings.cluster_name,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

        return None

    async def cleanup_old_reports(self) -> int:
        """Remove reports older than retention period.

        Returns:
            Number of reports deleted
        """
        cutoff_date = datetime.now() - timedelta(weeks=settings.retention_weeks)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                DELETE FROM reports
                WHERE cluster_name = ? AND generated_at < ?
                """,
                (settings.cluster_name, cutoff_date.isoformat()),
            )
            await db.commit()
            deleted_count = cursor.rowcount

        logger.info(
            "old_reports_cleaned",
            deleted_count=deleted_count,
            cutoff_date=cutoff_date.isoformat(),
        )

        return deleted_count

    async def get_report_stats(self) -> dict:
        """Get statistics about stored reports.

        Returns:
            Dict with report statistics
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT
                    COUNT(*) as total_reports,
                    SUM(report_size) as total_size,
                    MAX(generated_at) as latest_report_date,
                    MIN(generated_at) as oldest_report_date
                FROM reports
                WHERE cluster_name = ?
                """,
                (settings.cluster_name,),
            ) as cursor:
                row = await cursor.fetchone()

                return {
                    "total_reports": row[0] or 0,
                    "total_size_bytes": row[1] or 0,
                    "latest_report_date": row[2],
                    "oldest_report_date": row[3],
                }
