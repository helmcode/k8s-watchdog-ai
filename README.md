# K8s Watchdog AI 🐕

> Autonomous Kubernetes cluster observability with AI-powered weekly health reports

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

An intelligent Kubernetes monitoring agent that uses Claude AI to autonomously investigate cluster health, analyze metrics from Prometheus, and generate comprehensive weekly PDF reports delivered via Slack.

## ✨ Features

- 🤖 **AI-Powered Analysis**: Claude AI autonomously investigates cluster issues using direct Python tools
- 📊 **Prometheus Integration**: Analyzes metrics to detect resource inefficiencies (optional)
- 🔒 **Read-Only by Design**: All operations are read-only for safety
- 📄 **PDF Reports**: Professional HTML reports converted to PDF via WeasyPrint
- 📧 **Slack Integration**: Reports delivered via Slack with detailed tool usage information
- 🗄️ **Historical Tracking**: SQLite storage for report history
- 🚀 **REST API**: FastAPI server for on-demand report generation
- ⚡ **Graceful Degradation**: Works with or without Prometheus

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│              Kubernetes Cluster                      │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │       K8s Watchdog AI (FastAPI)              │   │
│  │                                              │   │
│  │  ┌────────────────────────────────────┐     │   │
│  │  │  Claude AI Agent                   │     │   │
│  │  │  - Autonomous investigation        │     │   │
│  │  │  - Tool selection & execution      │     │   │
│  │  │  - Report generation              │     │   │
│  │  └─────────┬──────────────────────────┘     │   │
│  │            │                                 │   │
│  │  ┌─────────▼──────────┐  ┌────────────────┐│   │
│  │  │ Kubernetes Tools   │  │ Prometheus     ││   │
│  │  │ - get pods/nodes   │  │ Tools          ││   │
│  │  │ - describe         │  │ - query        ││   │
│  │  │ - logs             │  │ - range query  ││   │
│  │  │ - events           │  │ - memory/cpu   ││   │
│  │  └────────────────────┘  └────────────────┘│   │
│  │                                              │   │
│  │  ┌────────────────────────────────────┐     │   │
│  │  │  Report Generator & Storage        │     │   │
│  │  │  - WeasyPrint (HTML → PDF)         │     │   │
│  │  │  - SQLite (history)                │     │   │
│  │  │  - Slack Files API v2              │     │   │
│  │  └────────────────────────────────────┘     │   │
│  └──────────────────┬───────────────────────────┘   │
└────────────────────┼─────────────────────────────────┘
                     │
                     ▼
              Slack Webhook
```

## 🚀 Quick Start

### Prerequisites

- Kubernetes cluster with kubectl access (or kubeconfig for local development)
- Anthropic API key ([Get one here](https://console.anthropic.com/))
- Slack webhook URL ([Create one](https://api.slack.com/messaging/webhooks))
- Slack Bot Token and Channel ID for file uploads ([Create bot](https://api.slack.com/apps))
- Prometheus running in cluster (optional - reports work without it)

### Local Development with Docker Compose

```bash
# 1. Clone the repository
git clone https://github.com/helmcode/k8s-watchdog-ai.git
cd k8s-watchdog-ai

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and settings

# 3. Run with docker-compose
docker-compose up -d

# 4. Trigger report generation
curl -X POST http://localhost:8000/report

# 5. Check status
curl http://localhost:8000/health

# 6. View logs
docker-compose logs -f
```

### Deploy to Kubernetes with Helm

```bash
# 1. Store secrets in Vault (if using Vault)
vault kv put helmcode_platform/k8s_watchdog_ai \
  ANTHROPIC_API_KEY="sk-ant-..." \
  SLACK_WEBHOOK_URL="https://hooks.slack.com/..." \
  SLACK_BOT_TOKEN="xoxb-..." \
  SLACK_CHANNEL="C123456789"

# 2. Install with Helm
helm install k8s-watchdog-ai ./helm \
  --namespace watchdog-ai \
  --create-namespace \
  --values ./helm/values/prod.yaml

# 3. Verify deployment
kubectl get pods -n watchdog-ai
kubectl logs -f deployment/k8s-watchdog-ai -n watchdog-ai
```

For detailed Helm deployment instructions, see [helm/README.md](helm/README.md).

### Deploy with ArgoCD

```bash
# Apply ArgoCD Application
kubectl apply -f helm/argocd/application.yaml

# Monitor deployment
argocd app get k8s-watchdog-ai
```

For ArgoCD configuration details, see [helm/argocd/README.md](helm/argocd/README.md).

## ⚙️ Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | - | Claude API key |
| `ANTHROPIC_MODEL` | ❌ | claude-sonnet-4-20250514 | AI model to use |
| `SLACK_WEBHOOK_URL` | ✅ | - | Slack webhook for messages |
| `SLACK_BOT_TOKEN` | ✅ | - | Bot token for file uploads |
| `SLACK_CHANNEL` | ✅ | - | Channel ID (e.g., C123456789) |
| `PROMETHEUS_URL` | ❌ | http://prometheus:9090 | Prometheus server URL |
| `CLUSTER_NAME` | ❌ | default | Cluster identifier |
| `EXCLUDED_NAMESPACES` | ❌ | kube-system,kube-public,... | Namespaces to exclude |
| `REPORT_LANGUAGE` | ❌ | spanish | Report language (spanish/english) |
| `SQLITE_PATH` | ❌ | /app/data/reports.db | SQLite database path |
| `LOG_LEVEL` | ❌ | INFO | Logging level |

See [.env.example](.env.example) for complete list.

## 📋 How It Works

1. **FastAPI Server**: Runs continuously, exposing `/report` and `/health` endpoints
2. **Trigger**: Can be called via HTTP POST or scheduled with Kubernetes CronJob
3. **AI Investigation**: 
   - Claude receives a system prompt with available tools
   - Agent autonomously decides what to investigate
   - Makes iterative queries to Kubernetes and Prometheus (if available)
4. **Analysis**: AI analyzes cluster health, resource usage, and metrics
5. **Report Generation**: Creates HTML report, converts to PDF with WeasyPrint
6. **Delivery**: Uploads PDF to Slack with detailed tool usage information
7. **Storage**: Saves report to SQLite for history tracking

### Example AI Investigation Flow

```
Claude: "Let me check the overall pod status"
→ Calls: kubectl_get_pods(namespace="default", all_namespaces=True)

Claude: "I see pod X has 15 restarts. Let me investigate"
→ Calls: kubectl_describe_pod(pod="X", namespace="production")
→ Calls: kubectl_get_pod_logs(pod="X", namespace="production", tail=100)

Claude: "This looks like OOMKilled. Let me check memory metrics"
→ Calls: prometheus_check_pod_memory(pod="X", namespace="production")
→ Calls: prometheus_query(query="container_memory_working_set_bytes{pod='X'}")

Claude: "Memory usage is consistently above request. Recommending increase"
→ Generates HTML report with specific recommendations
→ Report includes: issue analysis, metrics charts, action plan
```

### Tool Availability Detection

The system intelligently handles tool availability:

```
✅ Kubernetes API: 5 tool types used
   • Tools: kubectl_describe_pod, kubectl_get_deployments, kubectl_get_events, ...

❌ Prometheus: Connection failed
   • Prometheus not available: All connection attempts failed
   
   ℹ️ Report generated using Kubernetes data only
```

## 📊 Report Structure

Reports include:

1. **Executive Summary**: Overall health status (🟢🟡🔴)
2. **Top Issues**: 3-5 critical problems with severity levels
3. **Resource Analysis**: Over/under-provisioned workloads
4. **Prometheus Metrics**: CPU, memory, disk usage (when available)
5. **Action Plan**: Prioritized, actionable recommendations
6. **Footer**: Generated by Watchdog AI - Helmcode

The PDF report is accompanied by a Slack message showing:
- Report generation time
- Data sources used (Kubernetes API, Prometheus)
- Tool usage statistics
- Connection status for each service

## 🛠️ Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run locally (requires kubeconfig)
python -m src.main

# Format code
black src/
ruff check src/

# Type check
mypy src/

# Build Docker image
docker build -t k8s-watchdog-ai:latest .
```

## 🔐 Security

- **Read-only access**: All operations are read-only (get, list, watch, describe, logs)
- **RBAC**: Minimal permissions required in Kubernetes
- **No cluster modifications**: Agent cannot modify cluster state
- **Secrets management**: Kubernetes secrets for sensitive data
- **Connection errors**: Gracefully handles unavailable services

## 📚 API Endpoints

- `POST /report` - Generate and send report immediately (returns 202 Accepted)
- `GET /health` - Health check endpoint
- `GET /stats` - Report generation statistics

## 📚 Documentation

- [CLAUDE.md](CLAUDE.md) - Detailed technical documentation for AI assistants
- [Architecture Overview](#architecture) - System design
- [API Documentation](#api-endpoints) - REST endpoints

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [Anthropic Claude](https://www.anthropic.com/claude) - AI engine
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [WeasyPrint](https://weasyprint.org/) - PDF generation
- [Kubernetes Python Client](https://github.com/kubernetes-client/python) - K8s integration

---

**Made with ❤️ by [Helmcode](https://helmcode.com)**
