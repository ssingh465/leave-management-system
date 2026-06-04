# Leave Balance Service image.
# Built from the repo-root context so the shared package is available.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_PORT=8002

WORKDIR /app

COPY leave_balance_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY leave_balance_service/ ./leave_balance_service/

EXPOSE 8002

CMD ["sh", "-c", "uvicorn leave_balance_service.main:app --host 0.0.0.0 --port ${SERVICE_PORT}"]
