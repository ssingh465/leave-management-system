# API Gateway image.
# Built from the repo-root context (`docker-compose` uses `context: .`) so the
# shared package is available alongside the service package. Requirements are
# copied first to keep the pip layer cached across source-only changes.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_PORT=8080

WORKDIR /app

COPY api_gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY api_gateway/ ./api_gateway/

EXPOSE 8080

CMD ["sh", "-c", "uvicorn api_gateway.main:app --host 0.0.0.0 --port ${SERVICE_PORT}"]
