import asyncio
import json
import os
import sys
import tempfile

import structlog

from src.config import settings
from src.orchestrator.prompts import get_system_prompt

logger = structlog.get_logger()


class K8sWatchdogAgent:
    """Orchestrator for AI-powered Kubernetes cluster analysis.

    This agent uses Claude Code in headless mode with MCP servers
    to analyze cluster health.
    """

    def __init__(self) -> None:
        """Initialize the watchdog agent."""
        logger.info(
            "watchdog_agent_initialized",
            model=settings.anthropic_model,
            auth_method="claude_code_oauth",
        )

    def _build_mcp_config(self) -> dict:
        """Build MCP server configuration for Claude Code.

        Returns:
            MCP config dictionary
        """
        mcp_k8s_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "tools", "mcp_kubernetes.py"
        )
        mcp_prom_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "tools", "mcp_prometheus.py"
        )

        return {
            "mcpServers": {
                "kubernetes": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [mcp_k8s_path],
                },
                "prometheus": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [mcp_prom_path],
                    "env": {
                        "PROMETHEUS_URL": settings.prometheus_url,
                    },
                },
            }
        }

    async def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("tools_cleaned_up")

    async def generate_weekly_report(self) -> tuple[str, dict]:
        """Generate a weekly cluster health report using Claude Code headless mode.

        The agent will:
        1. Write system prompt and MCP config to temp files
        2. Invoke claude -p with MCP servers for K8s and Prometheus
        3. Parse JSON output to extract HTML report
        4. Return report and metadata

        Returns:
            Tuple of (HTML report as string, metadata dict)
        """
        logger.info("starting_weekly_report_generation", cluster=settings.cluster_name)

        # Build system prompt
        system_prompt = get_system_prompt(
            language=settings.report_language,
            cluster_name=settings.cluster_name,
        )

        # Build user prompt
        user_prompt = f"""Generate a weekly health report for cluster {settings.cluster_name}.

Investigate the current cluster state using the available tools:
1. Check pod and node status
2. Identify problems (restarts, errors, OOMKilled)
3. Analyze Prometheus metrics for resource issues
4. Compare actual usage vs requests/limits
5. Generate prioritized recommendations

Excluded namespaces: {', '.join(settings.excluded_namespaces)}

CRITICAL - RESPONSE FORMAT:
- Return ONLY the HTML code of the report
- DO NOT include any explanatory text, comments, or messages before or after the HTML
- DO NOT write phrases like "I see that...", "I'll proceed...", "Here is..."
- Your response must start directly with <!DOCTYPE html> or <html>
- If any tool is unavailable, simply omit that section from the report without mentioning it in the HTML
"""

        # Write temp files for MCP config and system prompt
        mcp_config = self._build_mcp_config()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="mcp_config_"
        ) as mcp_file:
            json.dump(mcp_config, mcp_file)
            mcp_config_path = mcp_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="system_prompt_"
        ) as prompt_file:
            prompt_file.write(system_prompt)
            prompt_path = prompt_file.name

        try:
            # Build claude command
            cmd = [
                "claude",
                "-p", user_prompt,
                "--output-format", "json",
                "--model", settings.anthropic_model,
                "--max-turns", str(settings.claude_max_turns),
                "--mcp-config", mcp_config_path,
                "--append-system-prompt-file", prompt_path,
                "--dangerously-skip-permissions",
                "--no-session-persistence",
            ]

            # Set environment with OAuth token
            env = {**os.environ}
            env["CLAUDE_CODE_OAUTH_TOKEN"] = settings.claude_code_oauth_token

            logger.info(
                "calling_claude_code_headless",
                model=settings.anthropic_model,
                max_turns=settings.claude_max_turns,
                timeout=settings.claude_timeout,
            )

            # Run claude CLI
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=settings.claude_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                raise RuntimeError(
                    f"Claude Code timed out after {settings.claude_timeout}s"
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if stderr_str:
                logger.debug("claude_code_stderr", stderr=stderr_str[:500])

            if process.returncode != 0:
                logger.error(
                    "claude_code_failed",
                    returncode=process.returncode,
                    stderr=stderr_str[:1000],
                )
                raise RuntimeError(
                    f"Claude Code exited with code {process.returncode}: {stderr_str[:500]}"
                )

            # Parse JSON output
            try:
                output = json.loads(stdout_str)
            except json.JSONDecodeError as e:
                logger.error(
                    "claude_code_invalid_json",
                    error=str(e),
                    stdout_preview=stdout_str[:500],
                )
                raise RuntimeError(f"Failed to parse Claude Code output: {str(e)}")

            # Extract HTML from result
            report_html = output.get("result", "")

            # Clean up any accidental text before HTML
            if "<!DOCTYPE" in report_html:
                report_html = report_html[report_html.index("<!DOCTYPE"):]
            elif "<html" in report_html.lower():
                html_start = report_html.lower().index("<html")
                report_html = report_html[html_start:]

            if not report_html.strip():
                raise RuntimeError("Claude Code returned empty result")

            # Build metadata
            metadata = {
                "model": settings.anthropic_model,
                "num_turns": output.get("num_turns", 0),
                "session_id": output.get("session_id", ""),
                "total_cost_usd": output.get("cost_usd", 0.0),
                "input_tokens": output.get("usage", {}).get("input_tokens", 0),
                "output_tokens": output.get("usage", {}).get("output_tokens", 0),
                "mcp_servers_used": ["kubernetes", "prometheus"],
                # Legacy fields for backward compatibility
                "tools_used": [],
                "tools_failed": [],
                "prometheus_available": None,  # Cannot be determined with Claude Code headless
            }

            logger.info(
                "weekly_report_generated",
                report_length=len(report_html),
                num_turns=metadata["num_turns"],
                cost_usd=metadata["total_cost_usd"],
            )

            return report_html, metadata

        finally:
            # Clean up temp files
            for path in [mcp_config_path, prompt_path]:
                try:
                    os.unlink(path)
                except OSError:
                    pass
