FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY services/worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/worker /app/services/worker
COPY services/__init__.py /app/services/__init__.py

EXPOSE 8001

CMD ["python", "/app/services/worker/entrypoint.py"]
