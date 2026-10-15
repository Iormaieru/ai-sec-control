# Worker de sincronización con Jira. Se construye desde la RAÍZ del repo
# (necesita backend/app, que reutiliza como librería; ver /.dockerignore):
#   docker build -f worker/Dockerfile .
FROM python:3.12-slim

RUN pip install --no-cache-dir uv \
    && useradd --create-home --uid 10001 app

WORKDIR /app

# Mismas dependencias (y versiones) que el backend.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/app ./app
COPY worker/aisec_worker ./aisec_worker

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER app

CMD ["python", "-m", "aisec_worker"]
