# Leave Request Service image.
# Built from the repo-root context so the shared package is available.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_PORT=8003

WORKDIR /app

COPY leave_request_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY leave_request_service/ ./leave_request_service/

EXPOSE 8003

CMD ["sh", "-c", "uvicorn leave_request_service.main:app --host 0.0.0.0 --port ${SERVICE_PORT}"]
