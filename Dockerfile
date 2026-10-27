FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 EVENT_HORIZON_BIND=0.0.0.0 EVENT_HORIZON_PORT=8000 EVENT_HORIZON_DATA_DIR=/app/data
WORKDIR /app
COPY requirements-azure.lock.txt ./
RUN pip install --no-cache-dir -r requirements-azure.lock.txt && useradd --uid 10001 --create-home appuser
COPY . .
RUN python -B -c "from demo_archive import validate; validate()" && chmod 0444 /app/data/full-match.sqlite3
RUN mkdir -p /app/data && chown -R 10001:10001 /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health/live', timeout=2).close()"
CMD ["python", "-B", "app.py"]
