FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

COPY requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN chown -R appuser:appuser /app

RUN chown -R appuser:appuser /app

USER appuser

CMD gunicorn --bind 0.0.0.0:${CONTAINER_PORT} --workers ${GUNICORN_WORKERS} app:app