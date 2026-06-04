# Manager Service image.
# Built from the repo-root context so the shared package is available.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_PORT=8004

WORKDIR /app

COPY manager_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY manager_service/ ./manager_service/

EXPOSE 8004

CMD ["sh", "-c", "uvicorn manager_service.main:app --host 0.0.0.0 --port ${SERVICE_PORT}"]
