"""MCP server for Kubernetes read-only operations."""

import json
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP
from kubernetes import client, config
from kubernetes.client import ApiException


mcp = FastMCP("kubernetes")

# Initialize Kubernetes client at module level
try:
    config.load_incluster_config()
    print("Loaded in-cluster Kubernetes config", file=sys.stderr)
except config.ConfigException:
    config.load_kube_config()
    print("Loaded kubeconfig", file=sys.stderr)

core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()


@mcp.tool()
def kubectl_get_pods(namespace: Optional[str] = None, label_selector: Optional[str] = None) -> str:
    """List pods in a namespace. Returns pod names, status, restarts, and age."""
    try:
        if namespace:
            pods = core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector or ""
            )
        else:
            pods = core_v1.list_pod_for_all_namespaces(
                label_selector=label_selector or ""
            )

        result = []
        for pod in pods.items:
            restarts = sum(cs.restart_count for cs in pod.status.container_statuses or [])
            result.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "restarts": restarts,
                "node": pod.spec.node_name,
                "age": str(pod.metadata.creation_timestamp)
            })

        return json.dumps(result, indent=2)
    except ApiException as e:
        return f"Kubernetes API error: {e.reason}"


@mcp.tool()
def kubectl_get_nodes() -> str:
    """List cluster nodes with status, roles, age, and version."""
    try:
        nodes = core_v1.list_node()

        result = []
        for node in nodes.items:
            conditions = {c.type: c.status for c in node.status.conditions}
            result.append({
                "name": node.metadata.name,
                "status": "Ready" if conditions.get("Ready") == "True" else "NotReady",
                "roles": node.metadata.labels.get("node-role.kubernetes.io/control-plane", "worker"),
                "version": node.status.node_info.kubelet_version,
                "age": str(node.metadata.creation_timestamp)
            })

        return json.dumps(result, indent=2)
    except ApiException as e:
        return f"Kubernetes API error: {e.reason}"


@mcp.tool()
def kubectl_describe_pod(name: str, namespace: str) -> str:
    """Get detailed information about a specific pod including events, conditions, and container states."""
    try:
        pod = core_v1.read_namespaced_pod(name=name, namespace=namespace)
        events = core_v1.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.name={name}"
        )

        result = {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status": pod.status.phase,
            "conditions": [
                {"type": c.type, "status": c.status, "reason": c.reason}
                for c in pod.status.conditions or []
            ],
            "containers": [
                {
                    "name": cs.name,
                    "ready": cs.ready,
                    "restarts": cs.restart_count,
                    "state": str(cs.state)
                }
                for cs in pod.status.container_statuses or []
            ],
            "events": [
                {
                    "type": e.type,
                    "reason": e.reason,
                    "message": e.message,
                    "time": str(e.last_timestamp)
                }
                for e in events.items[-10:]
            ]
        }

        return json.dumps(result, indent=2)
    except ApiException as e:
        return f"Kubernetes API error: {e.reason}"


@mcp.tool()
def kubectl_get_events(namespace: Optional[str] = None, limit: int = 50) -> str:
    """Get recent events in a namespace, useful for debugging issues."""
    try:
        if namespace:
            events = core_v1.list_namespaced_event(namespace=namespace)
        else:
            events = core_v1.list_event_for_all_namespaces()

        sorted_events = sorted(
            events.items,
            key=lambda e: e.last_timestamp or e.event_time,
            reverse=True
        )[:limit]

        result = [
            {
                "type": e.type,
                "reason": e.reason,
                "message": e.message,
                "object": f"{e.involved_object.kind}/{e.involved_object.name}",
                "namespace": e.metadata.namespace,
                "time": str(e.last_timestamp or e.event_time)
            }
            for e in sorted_events
        ]

        return json.dumps(result, indent=2)
    except ApiException as e:
        return f"Kubernetes API error: {e.reason}"


@mcp.tool()
def kubectl_get_deployments(namespace: Optional[str] = None) -> str:
    """List deployments with replicas status."""
    try:
        if namespace:
            deployments = apps_v1.list_namespaced_deployment(namespace=namespace)
        else:
            deployments = apps_v1.list_deployment_for_all_namespaces()

        result = [
            {
                "name": d.metadata.name,
                "namespace": d.metadata.namespace,
                "replicas": d.spec.replicas,
                "available": d.status.available_replicas or 0,
                "ready": d.status.ready_replicas or 0,
                "updated": d.status.updated_replicas or 0
            }
            for d in deployments.items
        ]

        return json.dumps(result, indent=2)
    except ApiException as e:
        return f"Kubernetes API error: {e.reason}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
