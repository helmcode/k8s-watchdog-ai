import json
from typing import Any
import httpx
import structlog

logger = structlog.get_logger()


class PrometheusTools:
    """Prometheus interaction tools for AI agent."""

    def __init__(self, prometheus_url: str):
        """Initialize Prometheus client.

        Args:
            prometheus_url: Base URL of Prometheus server
        """
        self.prometheus_url = prometheus_url.rstrip("/")
        logger.info("prometheus_tools_initialized", url=self.prometheus_url)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get Anthropic tool definitions for Prometheus operations.

        Returns:
            List of tool definitions
        """
        return [
            {
                "name": "prometheus_query",
                "description": "Execute instant PromQL query. Returns current values of metrics.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "PromQL query expression (e.g., 'container_memory_usage_bytes{pod=\"example\"}')"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "prometheus_query_range",
                "description": "Execute range PromQL query over a time period. Useful for trends.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "PromQL query expression"
                        },
                        "duration": {
                            "type": "string",
                            "description": "Time range to query (e.g., '1h', '24h', '7d'). Default: 1h"
                        },
                        "step": {
                            "type": "string",
                            "description": "Query resolution step (e.g., '1m', '5m'). Default: 1m"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "prometheus_check_pod_memory",
                "description": "Check memory usage vs limits for a specific pod. Helper to quickly identify OOM issues.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pod": {
                            "type": "string",
                            "description": "Pod name"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Pod namespace"
                        }
                    },
                    "required": ["pod", "namespace"]
                }
            },
            {
                "name": "prometheus_check_pod_cpu",
                "description": "Check CPU usage vs limits/requests for a specific pod.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pod": {
                            "type": "string",
                            "description": "Pod name"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Pod namespace"
                        }
                    },
                    "required": ["pod", "namespace"]
                }
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a Prometheus tool.

        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments

        Returns:
            Tool result as string
        """
        try:
            if tool_name == "prometheus_query":
                return await self._query(arguments["query"])
            elif tool_name == "prometheus_query_range":
                return await self._query_range(
                    arguments["query"],
                    arguments.get("duration", "1h"),
                    arguments.get("step", "1m")
                )
            elif tool_name == "prometheus_check_pod_memory":
                return await self._check_pod_memory(
                    arguments["pod"],
                    arguments["namespace"]
                )
            elif tool_name == "prometheus_check_pod_cpu":
                return await self._check_pod_cpu(
                    arguments["pod"],
                    arguments["namespace"]
                )
            else:
                return f"Unknown tool: {tool_name}"
        except RuntimeError:
            # Re-raise RuntimeError (like Prometheus not available) so it's tracked as tool failure
            raise
        except Exception as e:
            logger.error("prometheus_tool_error", tool=tool_name, error=str(e))
            return f"Error: {str(e)}"

    async def _query(self, query: str) -> str:
        """Execute instant query."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": query}
                )
                response.raise_for_status()
                data = response.json()

                if data["status"] != "success":
                    return f"Query failed: {data.get('error', 'unknown error')}"

                result = data["data"]["result"]
                if not result:
                    return "No data returned"

                # Format results
                formatted = []
                for item in result:
                    metric = item["metric"]
                    value = item["value"][1]  # [timestamp, value]
                    formatted.append({
                        "metric": metric,
                        "value": value
                    })

                return json.dumps(formatted, indent=2)
            except httpx.ConnectError as e:
                # Propagate connection errors so they're tracked as failures
                raise RuntimeError(f"Prometheus not available: {str(e)}")
            except httpx.HTTPError as e:
                return f"HTTP error: {str(e)}"

    async def _query_range(self, query: str, duration: str, step: str) -> str:
        """Execute range query."""
        import time

        # Parse duration to seconds
        duration_seconds = self._parse_duration(duration)
        end_time = int(time.time())
        start_time = end_time - duration_seconds

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{self.prometheus_url}/api/v1/query_range",
                    params={
                        "query": query,
                        "start": start_time,
                        "end": end_time,
                        "step": step
                    }
                )
                response.raise_for_status()
                data = response.json()

                if data["status"] != "success":
                    return f"Query failed: {data.get('error', 'unknown error')}"

                result = data["data"]["result"]
                if not result:
                    return "No data returned"

                # Simplify output - show min/max/avg for each metric
                formatted = []
                for item in result:
                    metric = item["metric"]
                    values = [float(v[1]) for v in item["values"]]

                    if values:
                        formatted.append({
                            "metric": metric,
                            "min": min(values),
                            "max": max(values),
                            "avg": sum(values) / len(values),
                            "current": values[-1],
                            "samples": len(values)
                        })

                return json.dumps(formatted, indent=2)
            except httpx.ConnectError as e:
                raise RuntimeError(f"Prometheus not available: {str(e)}")
            except httpx.HTTPError as e:
                return f"HTTP error: {str(e)}"

    async def _check_pod_memory(self, pod: str, namespace: str) -> str:
        """Check memory usage vs limits."""
        try:
            queries = {
                "usage": f'container_memory_usage_bytes{{pod="{pod}", namespace="{namespace}", container!=""}}',
                "limit": f'kube_pod_container_resource_limits{{pod="{pod}", namespace="{namespace}", resource="memory"}}',
                "request": f'kube_pod_container_resource_requests{{pod="{pod}", namespace="{namespace}", resource="memory"}}'
            }

            results = {}
            async with httpx.AsyncClient(timeout=30.0) as client:
                for name, query in queries.items():
                    try:
                        response = await client.get(
                            f"{self.prometheus_url}/api/v1/query",
                            params={"query": query}
                        )
                        response.raise_for_status()
                        data = response.json()

                        if data["status"] == "success" and data["data"]["result"]:
                            value = float(data["data"]["result"][0]["value"][1])
                            results[name] = value
                    except httpx.ConnectError:
                        raise
                    except Exception as e:
                        results[name] = f"Error: {str(e)}"

            # Calculate percentages
            analysis = {
                "pod": pod,
                "namespace": namespace,
                "usage_bytes": results.get("usage", "N/A"),
                "limit_bytes": results.get("limit", "N/A"),
                "request_bytes": results.get("request", "N/A")
            }

            if isinstance(results.get("usage"), (int, float)) and isinstance(results.get("limit"), (int, float)):
                analysis["usage_vs_limit_pct"] = (results["usage"] / results["limit"]) * 100

            return json.dumps(analysis, indent=2)
        except httpx.ConnectError as e:
            raise RuntimeError(f"Prometheus not available: {str(e)}")

    async def _check_pod_cpu(self, pod: str, namespace: str) -> str:
        """Check CPU usage vs limits."""
        try:
            queries = {
                "usage": f'rate(container_cpu_usage_seconds_total{{pod="{pod}", namespace="{namespace}", container!=""}}[5m])',
                "limit": f'kube_pod_container_resource_limits{{pod="{pod}", namespace="{namespace}", resource="cpu"}}',
                "request": f'kube_pod_container_resource_requests{{pod="{pod}", namespace="{namespace}", resource="cpu"}}'
            }

            results = {}
            async with httpx.AsyncClient(timeout=30.0) as client:
                for name, query in queries.items():
                    try:
                        response = await client.get(
                            f"{self.prometheus_url}/api/v1/query",
                            params={"query": query}
                        )
                        response.raise_for_status()
                        data = response.json()

                        if data["status"] == "success" and data["data"]["result"]:
                            value = float(data["data"]["result"][0]["value"][1])
                            results[name] = value
                    except httpx.ConnectError:
                        raise  # Propagate connection errors
                    except Exception as e:
                        results[name] = f"Error: {str(e)}"

            analysis = {
                "pod": pod,
                "namespace": namespace,
                "usage_cores": results.get("usage", "N/A"),
                "limit_cores": results.get("limit", "N/A"),
                "request_cores": results.get("request", "N/A")
            }

            if isinstance(results.get("usage"), (int, float)) and isinstance(results.get("limit"), (int, float)):
                analysis["usage_vs_limit_pct"] = (results["usage"] / results["limit"]) * 100

            return json.dumps(analysis, indent=2)
        except httpx.ConnectError as e:
            raise RuntimeError(f"Prometheus not available: {str(e)}")

    @staticmethod
    def _parse_duration(duration: str) -> int:
        """Parse duration string to seconds.

        Args:
            duration: Duration string (e.g., '1h', '24h', '7d')

        Returns:
            Duration in seconds
        """
        unit = duration[-1]
        value = int(duration[:-1])

        multipliers = {
            's': 1,
            'm': 60,
            'h': 3600,
            'd': 86400
        }

        return value * multipliers.get(unit, 3600)  # Default to hours
