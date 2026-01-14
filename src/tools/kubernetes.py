"""Kubernetes tools for Claude AI agent."""

import json
from typing import Any, Optional
from kubernetes import client, config
from kubernetes.client import ApiException
import structlog

logger = structlog.get_logger()


class KubernetesTools:
    """Kubernetes interaction tools for AI agent."""
    
    def __init__(self):
        """Initialize Kubernetes client."""
        try:
            # Try in-cluster config first (for K8s deployment)
            config.load_incluster_config()
            logger.info("loaded_incluster_k8s_config")
        except config.ConfigException:
            # Fall back to kubeconfig (for local development)
            config.load_kube_config()
            logger.info("loaded_kubeconfig")
        
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
    
    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get Anthropic tool definitions for Kubernetes operations.
        
        Returns:
            List of tool definitions
        """
        return [
            {
                "name": "kubectl_get_pods",
                "description": "List pods in a namespace. Returns pod names, status, restarts, and age.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Kubernetes namespace (default: all namespaces if empty)"
                        },
                        "label_selector": {
                            "type": "string",
                            "description": "Label selector (e.g., 'app=nginx')"
                        }
                    }
                }
            },
            {
                "name": "kubectl_get_nodes",
                "description": "List cluster nodes with status, roles, age, and version.",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "kubectl_describe_pod",
                "description": "Get detailed information about a specific pod including events, conditions, and container states.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Pod name"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Pod namespace"
                        }
                    },
                    "required": ["name", "namespace"]
                }
            },
            {
                "name": "kubectl_get_events",
                "description": "Get recent events in a namespace, useful for debugging issues.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Namespace (default: all)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max number of events to return (default: 50)"
                        }
                    }
                }
            },
            {
                "name": "kubectl_get_deployments",
                "description": "List deployments with replicas status.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Namespace (default: all)"
                        }
                    }
                }
            }
        ]
    
    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a Kubernetes tool.
        
        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments
            
        Returns:
            Tool result as string
        """
        try:
            if tool_name == "kubectl_get_pods":
                return await self._get_pods(
                    arguments.get("namespace"),
                    arguments.get("label_selector")
                )
            elif tool_name == "kubectl_get_nodes":
                return await self._get_nodes()
            elif tool_name == "kubectl_describe_pod":
                return await self._describe_pod(
                    arguments["name"],
                    arguments["namespace"]
                )
            elif tool_name == "kubectl_get_events":
                return await self._get_events(
                    arguments.get("namespace"),
                    arguments.get("limit", 50)
                )
            elif tool_name == "kubectl_get_deployments":
                return await self._get_deployments(arguments.get("namespace"))
            else:
                return f"Unknown tool: {tool_name}"
        except Exception as e:
            logger.error("k8s_tool_error", tool=tool_name, error=str(e))
            return f"Error: {str(e)}"
    
    async def _get_pods(self, namespace: Optional[str], label_selector: Optional[str]) -> str:
        """List pods."""
        try:
            if namespace:
                pods = self.core_v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector or ""
                )
            else:
                pods = self.core_v1.list_pod_for_all_namespaces(
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
    
    async def _get_nodes(self) -> str:
        """List nodes."""
        try:
            nodes = self.core_v1.list_node()
            
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
    
    async def _describe_pod(self, name: str, namespace: str) -> str:
        """Describe pod details."""
        try:
            pod = self.core_v1.read_namespaced_pod(name=name, namespace=namespace)
            events = self.core_v1.list_namespaced_event(
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
                    for e in events.items[-10:]  # Last 10 events
                ]
            }
            
            return json.dumps(result, indent=2)
        except ApiException as e:
            return f"Kubernetes API error: {e.reason}"
    
    async def _get_events(self, namespace: Optional[str], limit: int) -> str:
        """Get recent events."""
        try:
            if namespace:
                events = self.core_v1.list_namespaced_event(namespace=namespace)
            else:
                events = self.core_v1.list_event_for_all_namespaces()
            
            # Sort by timestamp
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
    
    async def _get_deployments(self, namespace: Optional[str]) -> str:
        """List deployments."""
        try:
            if namespace:
                deployments = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            else:
                deployments = self.apps_v1.list_deployment_for_all_namespaces()
            
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
