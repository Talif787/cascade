# syntax=docker/dockerfile:1.7
FROM python:3.14-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip build && pip install .

FROM python:3.14-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CASCADE_HTTP_HOST=0.0.0.0 \
    CASCADE_HTTP_PORT=8000

RUN groupadd --system cascade && useradd --system --gid cascade --home /app cascade
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
COPY docker-entrypoint.sh ./docker-entrypoint.sh

USER cascade
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/livez').status==200 else 1)"

CMD ["cascade"]
