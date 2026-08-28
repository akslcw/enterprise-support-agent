# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_RETRIES=5
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV HF_HOME=/opt/huggingface

WORKDIR /app

COPY requirements.txt ./

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --retries 10 --timeout 180 -r requirements.txt


COPY app ./app
COPY mcp_servers ./mcp_servers
COPY data ./data
COPY .chroma ./.chroma
COPY models/huggingface /opt/huggingface

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app /opt/huggingface

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.13-slim AS test

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1
ENV HF_HOME=/opt/huggingface

WORKDIR /app

COPY requirements.txt ./

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --retries 10 --timeout 180 -r requirements.txt

COPY app ./app
COPY mcp_servers ./mcp_servers
COPY data ./data
COPY .chroma ./.chroma
COPY models/huggingface /opt/huggingface
COPY tests ./tests

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app /opt/huggingface

USER appuser

CMD ["python", "-m", "pytest", "-q"]