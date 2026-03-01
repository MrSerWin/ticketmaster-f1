FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY src/ src/
COPY config.yaml .

RUN mkdir -p data \
    && useradd -m appuser \
    && chown -R appuser:appuser /app

USER appuser

CMD ["python", "-m", "src.monitor"]
