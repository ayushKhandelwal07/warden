# Warden API (FastAPI + MCP server + agent). The frontend is deployed separately (Vercel).
FROM python:3.11-slim

# git: the demo repo checkout (fix patches, PR history, sync to newer releases)
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY warden ./warden
COPY org ./org
COPY docker-entrypoint.sh .

ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
ENTRYPOINT ["sh", "docker-entrypoint.sh"]
