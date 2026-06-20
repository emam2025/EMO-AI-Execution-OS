FROM python:3.14-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-slim AS production

LABEL maintainer="Emo AI Team" \
      version="1.0.0-RC18" \
      description="Emo AI Execution OS — Production Image"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HOST=0.0.0.0 \
    PYTHONPATH=/app

RUN groupadd -r emo && useradd -r -g emo -d /app -s /sbin/nologin emo

WORKDIR /app

COPY core/ core/
COPY interfaces/ interfaces/
COPY routers/ routers/
COPY middleware/ middleware/
COPY main.py .
COPY VERSION .

RUN mkdir -p /app/data /app/logs /tmp && \
    chown -R emo:emo /app /tmp

USER emo

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD ["curl", "-f", "http://localhost:8080/api/status"]

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
