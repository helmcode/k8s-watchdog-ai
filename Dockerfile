# Stage 1: Node.js for Claude Code CLI
FROM node:22-slim AS node-base
RUN npm install -g @anthropic-ai/claude-code

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app

# WeasyPrint system deps
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev shared-mime-info && rm -rf /var/lib/apt/lists/*

# Copy Node.js + Claude CLI from stage 1
COPY --from=node-base /usr/local/bin/node /usr/local/bin/node
COPY --from=node-base /usr/local/bin/claude /usr/local/bin/claude
COPY --from=node-base /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN claude --version

# Create non-root user
RUN useradd -m -u 1000 watchdog

# Copy and install Python deps
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# Data dir and permissions
RUN mkdir -p /app/data && chown -R watchdog:watchdog /app/data

USER watchdog
ENV HOME=/home/watchdog

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
