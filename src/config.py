import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Claude Code Configuration
    claude_code_oauth_token: str
    anthropic_model: str = "claude-sonnet-4-20250514"
    claude_max_turns: int = 25
    claude_timeout: int = 300

    # Prometheus Configuration
    prometheus_url: str = "http://host.docker.internal:9090"
    kubeconfig_path: str = "~/.kube/config"

    # Cluster Configuration
    cluster_name: str = "default"
    client_name: str = "default"
    namespaces_exclude: str = "kube-system,kube-public,kube-node-lease"

    # Report Configuration
    report_language: str = "spanish"

    # Slack Configuration
    slack_webhook_url: str
    slack_bot_token: Optional[str] = None
    slack_channel: Optional[str] = None

    # Storage Configuration
    data_dir: str = "/app/data"
    retention_weeks: int = 2

    # Job Queue Configuration
    job_poll_interval: int = 5  # Seconds between queue polls
    job_max_retries: int = 3  # Maximum retry attempts for failed jobs

    # Logging Configuration
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def excluded_namespaces(self) -> list[str]:
        """Return list of excluded namespaces."""
        return [ns.strip() for ns in self.namespaces_exclude.split(",")]

    @property
    def sqlite_path(self) -> str:
        """Return path to SQLite database."""
        return os.path.join(self.data_dir, "watchdog.db")


# Global settings instance
settings = Settings()
