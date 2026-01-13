# K8s Observer 🔍

**Autonomous Kubernetes cluster monitoring with AI-powered insights**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Go Version](https://img.shields.io/badge/Go-1.22+-00ADD8?logo=go)](https://go.dev/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.19+-326CE5?logo=kubernetes)](https://kubernetes.io/)

K8s Observer is a lightweight Go application that runs inside your Kubernetes cluster to continuously monitor cluster health and deliver AI-analyzed reports directly to Slack.

## ✨ Features

- 🤖 **AI-Powered Analysis**: Uses Claude (Anthropic) to analyze cluster health and provide actionable insights
- 📊 **Automated Monitoring**: Collects cluster snapshots every 3 hours
- 📄 **Beautiful PDF Reports**: Generates styled HTML-based PDF reports with your brand colors
- 💬 **Slack Integration**: Sends weekly reports directly to your Slack channels
- 🗄️ **Zero Dependencies**: Uses embedded SQLite for data storage
- 🔒 **Secure**: Read-only RBAC permissions, runs as non-root
- 🌍 **Multi-language**: Generate reports in any language (English, Spanish, French, etc.)
- ⚙️ **Configurable**: Customize via environment variables

## 🎯 What It Does

K8s Observer monitors your Kubernetes cluster and generates concise weekly reports with:

1. **Executive Summary**: Quick health status (🟢 Green / 🟡 Yellow / 🔴 Red) and key metrics
2. **Main Issues**: Top 3-5 critical problems with severity, impact, and recommended actions
3. **Resource Optimization**: Identifies over-provisioned and at-risk workloads with cost-saving opportunities
4. **Action Plan**: Prioritized checklist of immediate actions to improve cluster health

## 🚀 Quick Start

### Prerequisites

- Kubernetes cluster (1.19+)
- [Anthropic API key](https://console.anthropic.com/) (for Claude AI)
- [Slack App](https://api.slack.com/apps) with:
  - Incoming webhook URL
  - Bot token with `chat:write`, `files:write`, and `channels:read` scopes

### Installation

1. **Clone the repository:**

```bash
git clone https://github.com/helmcode/k8s-watchdog-ai.git
cd k8s-watchdog-ai
```

2. **Configure secrets:**

Edit `manifests/secret.yaml` with your credentials:

```yaml
stringData:
  anthropic-api-key: "sk-ant-..."
  slack-webhook-url: "https://hooks.slack.com/services/..."
  slack-bot-token: "xoxb-..."
```

3. **Configure settings:**

Edit `manifests/configmap.yaml`:

```yaml
data:
  CLUSTER_NAME: "production"
  SLACK_CHANNEL: "C012AB3CDE4"  # Get from Slack channel URL
  REPORT_LANGUAGE: "english"    # or spanish, french, etc.
  REPORT_DAY: "monday"
  REPORT_TIME: "09:00"
```

4. **Deploy:**

```bash
kubectl apply -f manifests/
```

5. **Verify:**

```bash
kubectl get pods -l app=k8s-observer
kubectl logs -l app=k8s-observer -f
```

## 📋 Configuration

### Essential Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | - | Your Claude API key |
| `SLACK_WEBHOOK_URL` | ✅ | - | Slack incoming webhook |
| `SLACK_BOT_TOKEN` | ✅ | - | Slack bot token (`xoxb-...`) |
| `SLACK_CHANNEL` | ✅ | - | Channel ID (e.g., `C012AB3CDE4`) |
| `ANTHROPIC_MODEL` | ❌ | `claude-3-5-haiku-20241022` | Claude model to use |
| `REPORT_LANGUAGE` | ❌ | `english` | Report language |
| `CLUSTER_NAME` | ❌ | `default` | Cluster identifier |
| `SNAPSHOT_INTERVAL` | ❌ | `3h` | Collection frequency |
| `REPORT_DAY` | ❌ | `monday` | Weekly report day |
| `REPORT_TIME` | ❌ | `09:00` | Report time (24h) |

### Available Claude Models

- `claude-3-5-haiku-20241022` - Fast and cost-effective (recommended)
- `claude-3-5-sonnet-20241022` - Balanced performance
- `claude-sonnet-4-20250514` - Most capable

See [`.env.example`](.env.example) for all configuration options.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│            k8s-observer pod                  │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │Collector │─▶│ Analyzer │─▶│ Reporter  │  │
│  │(3h cron) │  │ (Claude) │  │ (Slack)   │  │
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

## 🛠️ Development

### Local Development

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env

# Build
go build -o bin/observer ./cmd/observer

# Run normally (continuous monitoring)
source .env && ./bin/observer

# Or run in test mode (one-time report)
source .env && ./bin/observer --test-report
```

### Test Mode

The `--test-report` flag is perfect for testing:
- Generates a report immediately
- Sends to Slack
- Exits after completion
- No need to wait for weekly schedule

### Build Docker Image

```bash
docker build -t your-registry/k8s-observer:latest .
docker push your-registry/k8s-observer:latest
```

### Testing with Local Cluster

```bash
# Create kind cluster
kind create cluster

# Install metrics-server (optional but recommended)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# For kind, patch metrics-server
kubectl patch -n kube-system deployment metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

# Deploy k8s-observer
kubectl apply -f manifests/
```

## 📊 Data Collected

Each snapshot includes:

- **Pods**: Status, restarts, restart reasons, resource requests/limits/actual usage
- **Nodes**: Capacity, allocatable resources, conditions
- **Events**: Warnings and errors from the cluster

## 🔒 Security

- ✅ Read-only ClusterRole (no write access)
- ✅ Runs as non-root user (UID 1000)
- ✅ Secrets stored in Kubernetes Secrets
- ✅ Persistent storage for database

## 🐛 Troubleshooting

### Pod not starting?

```bash
kubectl logs -l app=k8s-observer
```

Common issues:
- Missing API keys in secrets
- Invalid Slack channel ID (must be channel ID, not name)
- Metrics Server not installed (optional)

### No metrics data?

Verify Metrics Server:

```bash
kubectl get deployment metrics-server -n kube-system
kubectl top nodes
```

### Reports not sent?

Check logs:

```bash
kubectl logs -l app=k8s-observer | grep -i "report\|slack"
```

Verify:
- Slack webhook URL is correct
- Bot token has required scopes
- Channel ID is correct (starts with `C`, not `#channel-name`)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Powered by [Anthropic Claude](https://www.anthropic.com/) for AI analysis
- Built with ❤️ by the [HelmCloud](https://github.com/helmcode) team

## 🔗 Links

- [Documentation](https://github.com/helmcode/k8s-watchdog-ai/wiki)
- [Report Issues](https://github.com/helmcode/k8s-watchdog-ai/issues)
- [HelmCloud](https://helmcode.com)

---

Made with ❤️ by [HelmCloud](https://github.com/helmcode)
