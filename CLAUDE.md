# K8s Watchdog AI

Autonomous Kubernetes cluster observability agent with AI-powered weekly reports.

## Project Context

This is a Python FastAPI application that runs inside a Kubernetes cluster. It uses Claude AI with direct Python tools to autonomously investigate cluster health, analyze metrics from Prometheus (optional), and generate comprehensive weekly PDF reports sent to Slack.

**Owner:** Helmcode (Cristian)
**Purpose:** Internal tooling for cluster health monitoring with AI-powered insights, potentially offered as a service to clients in the future.

## Architecture (v0.2.0 - Direct Integration)

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│                                                              │
│            ┌─────────────────────────────────┐              │
│            │ K8s Watchdog AI (FastAPI)       │              │
│            │                                 │              │
│            │ ┌─────────────────────────┐    │              │
│            │ │ Claude AI Agent         │    │              │
│            │ │ - Autonomous analysis   │    │              │
│            │ │ - Tool selection        │    │              │
│            │ │ - HTML generation       │    │              │
│            │ └───────┬─────────────────┘    │              │
│            │         │                      │              │
│            │    ┌────▼────┐  ┌────────────┐│              │
│            │    │ K8s     │  │Prometheus  ││              │
│            │    │ Tools   │  │Tools       ││              │
│            │    │(Python) │  │(httpx)     ││              │
│            │    └─────────┘  └────────────┘│              │
│            │                                 │              │
│            │ ┌─────────────────────────┐    │              │
│            │ │ Report Generator        │    │              │
│            │ │ - WeasyPrint (PDF)      │    │              │
│            │ │ - SQLite (storage)      │    │              │
│            │ │ - Slack Files API v2    │    │              │
│            │ └─────────────────────────┘    │              │
│            └─────────┬───────────────────────┘              │
│                      │                                      │
└──────────────────────┼──────────────────────────────────────┘
                       │
                       ▼
                 Slack Webhook
```

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI 0.100+
- **AI:** Anthropic Claude API (claude-sonnet-4-20250514)
- **Kubernetes Client:** kubernetes>=28.1.0 (official Python client)
- **Prometheus Client:** httpx>=0.27.0 (async HTTP)
- **PDF Generation:** WeasyPrint 61.0 (HTML to PDF with system dependencies)
- **Storage:** SQLite (embedded, for report history)
- **Notifications:** Slack Files API v2 (3-step upload process)
- **Orchestration:** Kubernetes Deployment + optional CronJob

## Project Structure

```
k8s-watchdog-ai/
├── src/
│   ├── __init__.py
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Configuration management
│   ├── orchestrator/              # AI agent orchestration
│   │   ├── __init__.py
│   │   ├── agent.py               # Claude integration with direct tools
│   │   └── prompts.py             # System prompts
│   ├── tools/                     # Direct Python tools
│   │   ├── kubernetes.py          # K8s client (read-only)
│   │   └── prometheus.py          # Prometheus queries (optional)
│   ├── reporter/                  # Slack + PDF integration
│   │   ├── __init__.py
│   │   └── slack.py               # WeasyPrint + Files API v2
│   └── storage/                   # Report persistence
│       ├── __init__.py
│       └── reports.py             # SQLite storage
├── manifests/
│   └── watchdog-ai/               # Kubernetes manifests
│       ├── secret.yaml
│       ├── configmap.yaml
│       ├── pvc.yaml
│       ├── deployment.yaml
│       └── cronjob.yaml          # Optional: scheduled reports
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml             # Local development
├── README.md
└── CLAUDE.md
```

## Key Design Decisions

1. **Direct Tool Integration** - Claude AI directly calls Python functions (no external MCP servers)
3. **Python over Go** - Better AI/ML ecosystem, native MCP support in Anthropic SDK
4. **Read-only MCP servers** - Security by design, no cluster modifications
2. **FastAPI Server** - REST API for on-demand report generation and health checks
3. **Read-Only by Design** - All K8s and Prometheus operations are read-only
4. **Graceful Degradation** - Works with or without Prometheus (detects availability)
5. **SQLite for history** - Report archive with automatic cleanup
6. **PDF Reports** - WeasyPrint converts HTML to professional PDFs
7. **Detailed Metadata** - Tracks which tools were used, which failed, for transparency

## How It Works

### Report Generation Flow

1. **API trigger** (`POST /report`) or CronJob
2. **Agent initialization**: K8s and Prometheus tools loaded
3. **AI Investigation Phase**:
   - Claude receives system prompt with available tools
   - Agent autonomously decides what to query
   - Example: "Let me check pod status" → calls `kubectl_get_pods()`
   - Example: "High restarts, let me check logs" → calls `kubectl_get_pod_logs()`
   - Example: "Check memory metrics" → calls `prometheus_check_pod_memory()`
4. **Iterative analysis**: Claude makes multiple tool calls, analyzing results progressively
5. **Error handling**: If Prometheus unavailable, continues with K8s data only
6. **HTML generation**: Claude produces HTML report (cleaned of agent commentary)
7. **PDF conversion**: WeasyPrint converts HTML to PDF
8. **Storage**: Report saved to SQLite for historical tracking
9. **Slack delivery**: 
   - PDF uploaded via Files API v2 (3-step process)
   - Message includes tool usage statistics and generation time

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| ANTHROPIC_API_KEY | Yes | - | Claude API key |
| ANTHROPIC_MODEL | No | "claude-sonnet-4-20250514" | Claude model to use |
| PROMETHEUS_URL | No | "http://host.docker.internal:9090" | Prometheus server URL |
| CLUSTER_NAME | No | "default" | Identifier in reports |
| EXCLUDED_NAMESPACES | No | "kube-system,kube-public,..." | Namespaces to skip |
| REPORT_LANGUAGE | No | "spanish" | Report language (english, spanish) |
| SLACK_WEBHOOK_URL | Yes | - | Slack incoming webhook |
| SLACK_BOT_TOKEN | Yes | - | Slack bot token (for file uploads) |
| SLACK_CHANNEL | Yes | - | Slack channel ID (e.g., C012AB3CDE4) |
| SQLITE_PATH | No | "/app/data/reports.db" | SQLite database path |
| REPORT_RETENTION_DAYS | No | "30" | Report retention period |
| LOG_LEVEL | No | "INFO" | Log verbosity |

## Available Tools

### Kubernetes Tools (kubernetes.py)
- `kubectl_get_pods` - List pods across namespaces
- `kubectl_get_deployments` - List deployments
- `kubectl_get_nodes` - List cluster nodes
- `kubectl_describe_pod` - Detailed pod information
- `kubectl_get_pod_logs` - Fetch pod logs
- `kubectl_get_events` - Recent cluster events

### Prometheus Tools (prometheus.py) - Optional
- `prometheus_query` - Instant Prometheus query
- `prometheus_query_range` - Range query over time
- `prometheus_check_pod_memory` - Pod memory usage vs limits
- `prometheus_check_pod_cpu` - Pod CPU usage vs limits

### Connection Error Handling
- Prometheus tools raise `RuntimeError` if connection fails
- Agent tracks failures in metadata
- Report continues with available tools only
- Slack message shows which services were used/failed

## Report Generation

Weekly reports include:

1. **Health Summary:** Overall cluster status indicator
2. **Top Issues:** Critical problems with context and severity
3. **Resource Analysis:** Over/under-provisioned workloads
4. **Prometheus Metrics:** CPU, memory trends (when available)
5. **Event Analysis:** Recent warnings and errors
6. **Action Plan:** Prioritized, actionable recommendations
7. **Footer:** "Generated by Watchdog AI - Helmcode"

Slack message format:
```
📊 Weekly Health Report - [cluster-name]
🕒 Generated at: 2026-01-14 17:06:40
⏱️ Generation time: 74.5s

📦 Data Sources:
✅ Kubernetes API: 5 tool types used
   • Tools: kubectl_describe_pod, kubectl_get_deployments, ...
❌ Prometheus: Connection failed
   • Prometheus not available: All connection attempts failed

📝 Total tool calls: 8
```

## Development Guidelines

- Use Python best practices (type hints, docstrings, async/await)
- Keep functions small and focused
- Add structured logging with context
- Test Prometheus availability explicitly
- Ensure HTML output is clean (no agent commentary)
- Handle exceptions gracefully, continue with available data

## Build & Deploy

### Local Development

```bash
# Install dependencies
pip install -e .

# Copy environment file
cp .env.example .env
# Edit .env with your credentials

# Run with docker-compose
docker-compose up -d

# Trigger report
curl -X POST http://localhost:8000/report

# Check health
curl http://localhost:8000/health

# View logs
docker-compose logs -f
```

### Build Docker Image

```bash
docker build -t helmcode/k8s-watchdog-ai:latest .
```

### Deploy to Kubernetes

```bash
# Create namespace
kubectl create namespace observability

# Create secrets
kubectl create secret generic k8s-watchdog-secrets \
  --from-literal=anthropic-api-key=sk-ant-... \
  --from-literal=slack-webhook-url=https://hooks.slack.com/... \
  --from-literal=slack-bot-token=xoxb-... \
  --from-literal=slack-channel=C123456789 \
  -n observability

# Deploy watchdog AI
kubectl apply -f manifests/watchdog-ai/

# Check deployment
kubectl get pods -n observability
kubectl logs -f deployment/k8s-watchdog-ai -n observability
```

## Testing Locally

```bash
# With docker-compose (easiest, requires kubeconfig)
docker-compose up -d

# Trigger report
curl -X POST http://localhost:8000/report

# Check logs
docker-compose logs -f

# With Prometheus available
# Make sure Prometheus is accessible at http://host.docker.internal:9090

# Without Prometheus (will show connection failed in report)
# Just don't run Prometheus - agent will handle it gracefully
```

## Important Implementation Details

### Exception Handling in Tools
```python
# prometheus.py - Proper exception propagation
async def _query(self, query: str) -> str:
    try:
        response = await client.get(...)
        response.raise_for_status()
        return process_data(response)
    except httpx.ConnectError as e:
        # Propagate so agent tracks as failure
        raise RuntimeError(f"Prometheus not available: {str(e)}")
    except httpx.HTTPError as e:
        # Other errors returned as strings
        return f"HTTP error: {str(e)}"

# execute_tool must re-raise RuntimeError
async def execute_tool(self, tool_name: str, arguments: dict) -> str:
    try:
        # ... route to tool method ...
    except RuntimeError:
        # Re-raise for agent to catch and track
        raise
    except Exception as e:
        return f"Error: {str(e)}"
```

### Agent Tool Tracking
```python
# agent.py - Track successes and failures
try:
    result = await self._execute_tool(tool_name, tool_input)
    tools_used.append(tool_name)
except Exception as e:
    tools_failed.append({"tool": tool_name, "error": str(e)})

# Build metadata
prom_tools_used = [t for t in tools_used if t.startswith("prometheus_")]
prom_tools_failed = [f for f in tools_failed if f["tool"].startswith("prometheus_")]
prometheus_available = len(prom_tools_used) > 0 and len(prom_tools_failed) == 0
```

### PDF Generation
```python
# slack.py - WeasyPrint HTML to PDF
pdf_bytes = HTML(string=html_content).write_pdf()
# Requires system dependencies:
# - libpango-1.0-0
# - libpangocairo-1.0-0
# - libgdk-pixbuf-2.0-0
# - libffi-dev
# - shared-mime-info
```

### Slack Files API v2 (3-step process)
```python
# 1. Get upload URL
response = requests.post("slack.com/api/files.getUploadURLExternal")
upload_url = response["upload_url"]
file_id = response["file_id"]

# 2. Upload file to URL
requests.post(upload_url, data=pdf_bytes)

# 3. Complete upload
requests.post("slack.com/api/files.completeUploadExternal", json={
    "files": [{"id": file_id, "title": "report.pdf"}],
    "channel_id": channel
})
```

## Report Structure

Generated reports include:

1. **RESUMEN EJECUTIVO** (2-3 lines max)
   - Overall health status (🟢🟡🔴)
   - Brief cluster summary
   - Critical metrics

2. **PROBLEMAS PRINCIPALES** (Top 3-5 issues)
   - Severity badges (Critical/High/Medium)
   - Problem description
   - Impact
   - Recommended action

3. **OPTIMIZACIÓN DE RECURSOS**
   - Over-provisioned pods
   - At-risk pods (OOMKilled, CPU throttling)
   - Cost savings/risks

4. **MÉTRICAS DE PROMETHEUS** (when available)
   - Memory usage trends
   - CPU usage trends
   - Container resource requests vs actual usage

5. **PLAN DE ACCIÓN** (5-7 prioritized items)
   - Numbered action list
   - Most critical first
   - Specific and actionable

6. **FOOTER**
   - "Reporte generado automáticamente por Watchdog AI"
   - "💡 Helmcode - Infraestructura confiable para aplicaciones en la nube"

## Recent Changes (v0.2.0)

1. **Removed MCP architecture** - Direct Python tools integration (simpler, faster)
2. **Added PDF generation** - WeasyPrint converts HTML to professional PDFs
3. **Fixed Prometheus detection** - Properly detects when service unavailable
4. **Tool usage metadata** - Tracks which tools used/failed for transparency
5. **Slack Files API v2** - 3-step upload process for reliable PDF delivery
6. **Exception handling** - RuntimeError propagation for proper failure tracking
7. **Graceful degradation** - Works with only Kubernetes when Prometheus down

## Known Issues & Solutions

**Issue**: Prometheus reports success when offline
**Solution**: In `prometheus.py`, catch `httpx.ConnectError` separately and raise `RuntimeError`. In `execute_tool`, re-raise `RuntimeError` instead of catching all exceptions.

**Issue**: WeasyPrint Docker build fails with disk space
**Solution**: Run `docker system prune` to free space before building

**Issue**: Agent commentary appearing in PDF
**Solution**: System prompt explicitly states "CRÍTICO - FORMATO DE RESPUESTA: Devuelve ÚNICAMENTE el código HTML". Agent strips text before `<!DOCTYPE` or `<html`.

## Future Considerations

- Multi-cluster consolidated reports
- Historical trend analysis (week-over-week)
- Web dashboard for report browsing
- Interactive Slack actions (approve recommendations)
- Auto-remediation capabilities (with approval workflows)
- Cost analysis integration
- GitOps integration (auto-create MRs for resource adjustments)
