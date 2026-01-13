# K8s Observer

Autonomous Kubernetes cluster observability agent with AI-powered weekly reports.

## Project Context

This is a Go application that runs as a single pod inside a Kubernetes cluster. It collects cluster state data periodically, stores it locally, and generates AI-analyzed weekly reports sent to Slack.

**Owner:** HelmCloud (Cristian)
**Purpose:** Internal tooling for cluster health monitoring, potentially offered as a service to clients in the future.

## Architecture
```
┌─────────────────────────────────────────────┐
│            k8s-observer pod                  │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │Collector │─▶│ Analyzer │─▶│ Reporter  │  │
│  │(periodic)│  │ (Claude) │  │ (Slack)   │  │
│  └──────────┘  └──────────┘  └───────────┘  │
│       │              ▲                       │
│       ▼              │                       │
│  ┌──────────────────────────────────────┐   │
│  │            SQLite Storage             │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
        │
        ▼
   K8s API (read-only)
```

## Tech Stack

- **Language:** Go 1.22+
- **K8s Client:** client-go
- **LLM:** Anthropic Claude API (claude-sonnet-4-20250514)
- **Storage:** SQLite (embedded)
- **Notifications:** Slack webhooks

## Project Structure
```
k8s-observer/
├── cmd/
│   └── observer/
│       └── main.go           # Entry point
├── internal/
│   ├── collector/            # K8s data collection
│   │   ├── collector.go
│   │   ├── pods.go
│   │   ├── nodes.go
│   │   ├── events.go
│   │   └── metrics.go
│   ├── storage/              # SQLite operations
│   │   ├── storage.go
│   │   ├── models.go
│   │   └── migrations.go
│   ├── analyzer/             # Claude integration
│   │   ├── analyzer.go
│   │   └── prompts.go
│   ├── reporter/             # Slack integration
│   │   ├── reporter.go
│   │   └── formatter.go
│   ├── scheduler/            # Cron-like scheduling
│   │   └── scheduler.go
│   └── config/               # Configuration management
│       └── config.go
├── manifests/                # Kubernetes manifests
│   ├── deployment.yaml
│   ├── rbac.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   └── pvc.yaml
├── Dockerfile
├── go.mod
├── go.sum
├── README.md
└── CLAUDE.md
```

## Key Design Decisions

1. **One observer per cluster** - Simplifies deployment and avoids multi-cluster complexity
2. **SQLite for storage** - No external dependencies, data locality, simple backup
3. **3-hour snapshot interval** - Balance between granularity and storage/API load
4. **2-week retention** - Enough for week-over-week comparison without excessive storage
5. **Namespace exclusion via env var** - Flexible filtering without code changes

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| ANTHROPIC_API_KEY | Yes | - | Claude API key |
| ANTHROPIC_MODEL | No | "claude-3-5-haiku-20241022" | Claude model to use (haiku=cheapest, sonnet=balanced, opus=best) |
| REPORT_LANGUAGE | No | "english" | Report language (english, spanish, french, german, etc.) |
| SLACK_WEBHOOK_URL | Yes | - | Slack incoming webhook |
| SLACK_BOT_TOKEN | Yes | - | Slack bot token (for PDF uploads) |
| SLACK_CHANNEL | Yes | - | Slack channel ID (e.g., C012AB3CDE4) |
| CLUSTER_NAME | No | "default" | Identifier in reports |
| NAMESPACES_EXCLUDE | No | "kube-system,kube-public,kube-node-lease" | Namespaces to skip |
| SNAPSHOT_INTERVAL | No | "3h" | Collection frequency |
| REPORT_DAY | No | "monday" | Weekly report day |
| REPORT_TIME | No | "09:00" | Report time (24h format) |
| RETENTION_WEEKS | No | "2" | Data retention period |
| LOG_LEVEL | No | "info" | Log verbosity |

## Data Collection

Each snapshot collects:

- **Pods:** name, namespace, status, restarts, restart reasons, age
- **Resources:** CPU/memory requests, limits, and actual usage (from metrics API)
- **Events:** warnings and errors from the last snapshot interval
- **Nodes:** status, capacity, allocatable resources, conditions

## Report Generation

Weekly reports include:

1. **Health Score:** Overall cluster status (🟢🟡🔴)
2. **Top Issues:** 3-5 most important problems with severity
3. **Resource Optimization:** Over/under-provisioned workloads
4. **Trends:** Comparison with previous week
5. **Action Items:** Prioritized recommendations

## Development Guidelines

- Use Go idioms (error handling, naming conventions)
- Keep functions small and focused
- Add context to errors for debugging
- Log at appropriate levels (debug for verbose, info for operations, error for failures)
- Test with a local kind/minikube cluster before deploying

## Build & Deploy
```bash
# Build
go build -o bin/observer ./cmd/observer

# Docker
docker build -t helmcloud/k8s-observer:latest .

# Deploy
kubectl apply -f manifests/
```

## Testing Locally
```bash
# Run with local kubeconfig
export KUBECONFIG=~/.kube/config
export ANTHROPIC_API_KEY=sk-...
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...
export SLACK_CHANNEL=#test-channel
go run ./cmd/observer
```

## Future Considerations (Post-MVP)

- Real-time critical alerts
- Integration with existing observability stack (ClickHouse, Prometheus)
- Web dashboard for historical data
- Multi-cluster consolidated reports
- Slack interactive actions for applying recommendations
