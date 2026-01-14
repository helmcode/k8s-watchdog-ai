import structlog
from anthropic import Anthropic
from typing import Any

from src.config import settings
from src.orchestrator.prompts import get_system_prompt
from src.tools.kubernetes import KubernetesTools
from src.tools.prometheus import PrometheusTools

logger = structlog.get_logger()


class K8sWatchdogAgent:
    """Orchestrator for AI-powered Kubernetes cluster analysis.

    This agent uses Claude AI with direct Kubernetes and Prometheus tools
    to analyze cluster health.
    """

    def __init__(self) -> None:
        """Initialize the watchdog agent."""
        self.anthropic = Anthropic(api_key=settings.anthropic_api_key)
        self.k8s_tools: KubernetesTools | None = None
        self.prom_tools: PrometheusTools | None = None

        logger.info(
            "watchdog_agent_initialized",
            model=settings.anthropic_model,
        )

    async def _initialize_tools(self) -> list[dict[str, Any]]:
        """Initialize Kubernetes and Prometheus tools.

        Returns:
            List of tool definitions for Claude
        """
        if self.k8s_tools and self.prom_tools:
            # Already initialized
            tools = self.k8s_tools.get_tool_definitions()
            tools.extend(self.prom_tools.get_tool_definitions())
            return tools

        # Initialize tools
        self.k8s_tools = KubernetesTools()
        self.prom_tools = PrometheusTools(settings.prometheus_url)

        # Get tool definitions
        tools = self.k8s_tools.get_tool_definitions()
        tools.extend(self.prom_tools.get_tool_definitions())

        logger.info("tools_initialized", count=len(tools))
        return tools

    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by routing to appropriate handler.

        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments

        Returns:
            Tool result as string
        """
        if tool_name.startswith("kubectl_"):
            if not self.k8s_tools:
                raise RuntimeError("Kubernetes tools not initialized")
            return await self.k8s_tools.execute_tool(tool_name, arguments)
        elif tool_name.startswith("prometheus_"):
            if not self.prom_tools:
                raise RuntimeError("Prometheus tools not initialized")
            return await self.prom_tools.execute_tool(tool_name, arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self.k8s_tools = None
        self.prom_tools = None
        logger.info("tools_cleaned_up")

    async def generate_weekly_report(self) -> tuple[str, dict]:
        """Generate a weekly cluster health report using AI analysis.

        The agent will autonomously:
        1. Query Kubernetes for cluster state
        2. Query Prometheus for metrics
        3. Analyze the data
        4. Generate an HTML report

        Returns:
            Tuple of (HTML report as string, metadata dict with tools info)
        """
        logger.info("starting_weekly_report_generation", cluster=settings.cluster_name)

        # Track tool usage for metadata
        tools_used = []
        tools_failed = []

        # Initialize tools
        tools = await self._initialize_tools()

        if not tools:
            raise RuntimeError("No tools available")

        logger.info("tools_loaded", count=len(tools))

        # Build system prompt
        system_prompt = get_system_prompt(
            language=settings.report_language,
            cluster_name=settings.cluster_name,
        )

        # Initial message to Claude
        messages = [
            {
                "role": "user",
                "content": f"""Genera un reporte semanal de salud del cluster {settings.cluster_name}.

Investiga el estado actual del cluster usando las herramientas disponibles:
1. Revisa el estado de pods y nodes
2. Identifica problemas (restarts, errores, OOMKilled)
3. Analiza métricas de Prometheus para detectar issues de recursos
4. Compara uso real vs requests/limits
5. Genera recomendaciones priorizadas

Namespaces excluidos del análisis: {', '.join(settings.excluded_namespaces)}

CRÍTICO - FORMATO DE RESPUESTA:
- Devuelve ÚNICAMENTE el código HTML del reporte
- NO incluyas ningún texto explicativo, comentario o mensaje antes o después del HTML
- NO escribas frases como "Veo que...", "Voy a proceder...", "Aquí está..."
- Tu respuesta debe empezar directamente con <!DOCTYPE html> o <html>
- Si alguna herramienta no está disponible, simplemente omite esa sección del reporte sin mencionarlo en el HTML
"""
            }
        ]

        # Call Claude with tools
        logger.info("calling_claude_api", tools_available=len(tools))

        response = self.anthropic.messages.create(
            model=settings.anthropic_model,
            max_tokens=16384,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        # Handle tool calls in a loop (Claude agentic behavior)
        while response.stop_reason == "tool_use":
            logger.info("claude_requesting_tool_calls", tool_count=len([
                block for block in response.content if block.type == "tool_use"
            ]))

            # Execute tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    logger.info("executing_tool", tool=tool_name, input=tool_input)

                    try:
                        result = await self._execute_tool(tool_name, tool_input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        })
                        logger.info("tool_execution_successful", tool=tool_name)
                        tools_used.append(tool_name)
                    except Exception as e:
                        logger.error("tool_execution_failed", tool=tool_name, error=str(e))
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {str(e)}",
                            "is_error": True,
                        })
                        tools_failed.append({"tool": tool_name, "error": str(e)})
                        # Don't add to tools_used when there's an exception

            # Continue conversation with tool results
            messages.append({
                "role": "assistant",
                "content": response.content,
            })
            messages.append({
                "role": "user",
                "content": tool_results,
            })

            response = self.anthropic.messages.create(
                model=settings.anthropic_model,
                max_tokens=16384,
                system=system_prompt,
                messages=messages,
                tools=tools,
            )

        # Extract final report
        report_html = ""
        for block in response.content:
            if hasattr(block, "text"):
                report_html += block.text

        # Clean up any accidental text before HTML
        # Remove any text before the first HTML tag
        if "<!DOCTYPE" in report_html:
            report_html = report_html[report_html.index("<!DOCTYPE"):]
        elif "<html" in report_html.lower():
            html_start = report_html.lower().index("<html")
            report_html = report_html[html_start:]

        # Build metadata
        # Separate tools by category
        k8s_tools_used = [t for t in tools_used if t.startswith("kubectl_")]
        prom_tools_used = [t for t in tools_used if t.startswith("prometheus_")]
        prom_tools_failed = [f for f in tools_failed if f["tool"].startswith("prometheus_")]

        # Prometheus is available only if it was used successfully
        prometheus_available = len(prom_tools_used) > 0 and len(prom_tools_failed) == 0

        metadata = {
            "tools_used": list(set(tools_used)),  # Remove duplicates
            "tools_failed": tools_failed,
            "tools_available": len(tools),
            "total_tool_calls": len(tools_used),
            "k8s_tools_used": list(set(k8s_tools_used)),
            "prom_tools_used": list(set(prom_tools_used)),
            "prom_tools_failed": prom_tools_failed,
            "prometheus_available": prometheus_available,
        }

        logger.info(
            "weekly_report_generated",
            report_length=len(report_html),
            stop_reason=response.stop_reason,
            tools_metadata=metadata,
        )

        return report_html, metadata
