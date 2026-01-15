# K8s Watchdog AI Helm Chart

Helm chart for deploying K8s Watchdog AI - Autonomous Kubernetes observability with AI-powered weekly reports.

## Prerequisites

- Kubernetes 1.23+
- Helm 3.8+
- HashiCorp Vault Operator installed
- Traefik (optional, for ingress)

## Installation

### 1. Prepare Vault Secrets

Store the following secrets in Vault at path: `helmcode_platform/k8s_watchdog_ai`

Required keys:
- `ANTHROPIC_API_KEY`: Your Anthropic Claude API key
- `SLACK_WEBHOOK_URL`: Slack webhook URL for notifications
- `SLACK_BOT_TOKEN`: Slack bot token for file uploads
- `SLACK_CHANNEL`: Slack channel ID (e.g., C123456789)

Optional keys:
- `PROMETHEUS_URL`: Prometheus server URL (default: http://prometheus:9090)
- `CLUSTER_NAME`: Cluster identifier for reports (default: default)
- `EXCLUDED_NAMESPACES`: Comma-separated namespaces to exclude
- `REPORT_LANGUAGE`: Report language (default: spanish)
- `LOG_LEVEL`: Logging level (default: INFO)

Example Vault command:
```bash
vault kv put helmcode_platform/k8s_watchdog_ai \
  ANTHROPIC_API_KEY="sk-ant-..." \
  SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..." \
  SLACK_BOT_TOKEN="xoxb-..." \
  SLACK_CHANNEL="C123456789" \
  CLUSTER_NAME="production" \
  REPORT_LANGUAGE="spanish"
```

### 2. Install via Helm

```bash
# Install in watchdog-ai namespace
# No image pull secrets needed - repository is public
helm install k8s-watchdog-ai ./helm \
  --namespace watchdog-ai \
  --create-namespace \
  --values ./helm/values/prod.yaml
```

### 3. Install via ArgoCD

Create an ArgoCD Application:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: k8s-watchdog-ai
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/helmcode/k8s-watchdog-ai.git
    targetRevision: main
    path: helm
    helm:
      valueFiles:
        - values/prod.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: watchdog-ai
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

## Configuration

### Key Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas (must be 1 for SQLite) | `1` |
| `image.repository` | Container image repository | `ghcr.io/helmcode/k8s-watchdog-ai` |
| `image.tag` | Container image tag | `latest` |
| `imageCredentials.registry` | Container registry (for private repos) | `ghcr.io` |
| `vault.secrets.env.path` | Vault path for secrets | `k8s_watchdog_ai` |
| `persistence.size` | PVC size for SQLite database | `5Gi` |
| `resources.limits.memory` | Memory limit | `1Gi` |
| `service.type` | Kubernetes service type | `ClusterIP` |
| `ingress.enabled` | Enable ingress (not recommended - no auth) | `false` |

### RBAC Permissions

The chart creates a ClusterRole with read-only access:
- Pods: get, list, watch, logs
- Nodes: get, list, watch
- Events: get, list, watch
- Deployments: get, list
- Namespaces: get, list, watch

## Usage

### Manual Report Generation

Trigger a report manually:

```bash
kubectl exec -n watchdog-ai deployment/k8s-watchdog-ai -- \
  curl -X POST http://localhost:8000/report
```

Or from another pod:

```bash
kubectl run -n watchdog-ai curl --rm -i --restart=Never \
  --image=curlimages/curl:8.5.0 -- \
  curl -X POST http://k8s-watchdog-ai.watchdog-ai.svc.cluster.local/report
```

### Scheduled Reports

The chart includes a CronJob that triggers report generation daily at 9:00 AM.

To change the schedule, modify the CronJob:

```bash
kubectl edit cronjob -n watchdog-ai k8s-watchdog-ai-report-trigger
```

Or override in values:

```yaml
# Custom schedule (every Monday at 9:00 AM)
cronjob:
  schedule: "0 9 * * 1"
```

### Check Logs

```bash
# API logs
kubectl logs -n watchdog-ai deployment/k8s-watchdog-ai -f

# CronJob logs
kubectl logs -n watchdog-ai job/k8s-watchdog-ai-report-trigger-xxxxx
```

### View Report History

```bash
# Get stats
kubectl exec -n watchdog-ai deployment/k8s-watchdog-ai -- \
  curl http://localhost:8000/stats
```

## Troubleshooting

### Reports Not Generated

1. Check API health:
   ```bash
   kubectl exec -n watchdog-ai deployment/k8s-watchdog-ai -- \
     curl http://localhost:8000/health
   ```

2. Verify Vault secrets are loaded:
   ```bash
   kubectl get secret -n watchdog-ai k8s-watchdog-ai-env-secret
   kubectl get vaultstaticsecret -n watchdog-ai
   ```

3. Check RBAC permissions:
   ```bash
   kubectl auth can-i get pods --as=system:serviceaccount:watchdog-ai:k8s-watchdog-ai-sa
   ```

### Prometheus Connection Issues

If Prometheus is unavailable, the system will continue generating reports using only Kubernetes data. Check logs for:

```
tool_execution_failed tool=prometheus_query error='Prometheus not available...'
```

This is expected and handled gracefully.

## Upgrading

```bash
helm upgrade k8s-watchdog-ai ./helm \
  --namespace watchdog-ai \
  --values ./helm/values/prod.yaml
```

## Uninstalling

```bash
helm uninstall k8s-watchdog-ai --namespace watchdog-ai
```

**Note**: PVC will not be automatically deleted. To remove:

```bash
kubectl delete pvc -n watchdog-ai k8s-watchdog-ai-data
```

## Security Considerations

- No secrets are stored in the chart - all managed via Vault
- Service runs as non-root user (UID 1000)
- Read-only Kubernetes access via RBAC
- No ingress by default (API has no authentication)
- Pod security context with dropped capabilities

## Support

For issues and questions:
- GitHub: https://github.com/helmcode/k8s-watchdog-ai
- Email: team@helmcode.com
