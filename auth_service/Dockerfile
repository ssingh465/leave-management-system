# Auth Service image.
# Built from the repo-root context so the shared package is available.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_PORT=8001

WORKDIR /app

COPY auth_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY auth_service/ ./auth_service/

EXPOSE 8001

CMD ["sh", "-c", "uvicorn auth_service.main:app --host 0.0.0.0 --port ${SERVICE_PORT}"]
