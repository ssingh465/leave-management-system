# Notification Service image.
# Built from the repo-root context so the shared package is available.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_PORT=8005

WORKDIR /app

COPY notification_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY notification_service/ ./notification_service/

EXPOSE 8005

CMD ["sh", "-c", "uvicorn notification_service.main:app --host 0.0.0.0 --port ${SERVICE_PORT}"]
