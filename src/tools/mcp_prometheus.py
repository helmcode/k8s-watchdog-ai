"""MCP server for Prometheus read-only operations."""

import json
import os
import sys
import time
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("prometheus")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://host.docker.internal:9090").rstrip("/")
print(f"Prometheus URL: {PROMETHEUS_URL}", file=sys.stderr)


def _parse_duration(duration: str) -> int:
    """Parse duration string to seconds."""
    unit = duration[-1]
    value = int(duration[:-1])
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers.get(unit, 3600)


@mcp.tool()
def prometheus_query(query: str) -> str:
    """Execute instant PromQL query. Returns current values of metrics."""
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query}
            )
            response.raise_for_status()
            data = response.json()

            if data["status"] != "success":
                return f"Query failed: {data.get('error', 'unknown error')}"

            result = data["data"]["result"]
            if not result:
                return "No data returned"

            formatted = []
            for item in result:
                formatted.append({
                    "metric": item["metric"],
                    "value": item["value"][1]
                })

            return json.dumps(formatted, indent=2)
    except httpx.ConnectError as e:
        return f"Prometheus not available: {str(e)}"
    except httpx.HTTPError as e:
        return f"HTTP error: {str(e)}"


@mcp.tool()
def prometheus_query_range(query: str, duration: str = "1h", step: str = "1m") -> str:
    """Execute range PromQL query over a time period. Useful for trends."""
    try:
        duration_seconds = _parse_duration(duration)
        end_time = int(time.time())
        start_time = end_time - duration_seconds

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{PROMETHEUS_URL}/api/v1/query_range",
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

            formatted = []
            for item in result:
                values = [float(v[1]) for v in item["values"]]
                if values:
                    formatted.append({
                        "metric": item["metric"],
                        "min": min(values),
                        "max": max(values),
                        "avg": sum(values) / len(values),
                        "current": values[-1],
                        "samples": len(values)
                    })

            return json.dumps(formatted, indent=2)
    except httpx.ConnectError as e:
        return f"Prometheus not available: {str(e)}"
    except httpx.HTTPError as e:
        return f"HTTP error: {str(e)}"


@mcp.tool()
def prometheus_check_pod_memory(pod: str, namespace: str) -> str:
    """Check memory usage vs limits for a specific pod. Helper to quickly identify OOM issues."""
    try:
        queries = {
            "usage": f'container_memory_usage_bytes{{pod="{pod}", namespace="{namespace}", container!=""}}',
            "limit": f'kube_pod_container_resource_limits{{pod="{pod}", namespace="{namespace}", resource="memory"}}',
            "request": f'kube_pod_container_resource_requests{{pod="{pod}", namespace="{namespace}", resource="memory"}}'
        }

        results = {}
        with httpx.Client(timeout=30.0) as client:
            for name, query in queries.items():
                try:
                    response = client.get(
                        f"{PROMETHEUS_URL}/api/v1/query",
                        params={"query": query}
                    )
                    response.raise_for_status()
                    data = response.json()

                    if data["status"] == "success" and data["data"]["result"]:
                        value = float(data["data"]["result"][0]["value"][1])
                        results[name] = value
                except httpx.ConnectError as e:
                    return f"Prometheus not available: {str(e)}"
                except Exception as e:
                    results[name] = f"Error: {str(e)}"

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
        return f"Prometheus not available: {str(e)}"


@mcp.tool()
def prometheus_check_pod_cpu(pod: str, namespace: str) -> str:
    """Check CPU usage vs limits/requests for a specific pod."""
    try:
        queries = {
            "usage": f'rate(container_cpu_usage_seconds_total{{pod="{pod}", namespace="{namespace}", container!=""}}[5m])',
            "limit": f'kube_pod_container_resource_limits{{pod="{pod}", namespace="{namespace}", resource="cpu"}}',
            "request": f'kube_pod_container_resource_requests{{pod="{pod}", namespace="{namespace}", resource="cpu"}}'
        }

        results = {}
        with httpx.Client(timeout=30.0) as client:
            for name, query in queries.items():
                try:
                    response = client.get(
                        f"{PROMETHEUS_URL}/api/v1/query",
                        params={"query": query}
                    )
                    response.raise_for_status()
                    data = response.json()

                    if data["status"] == "success" and data["data"]["result"]:
                        value = float(data["data"]["result"][0]["value"][1])
                        results[name] = value
                except httpx.ConnectError as e:
                    return f"Prometheus not available: {str(e)}"
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
        return f"Prometheus not available: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
