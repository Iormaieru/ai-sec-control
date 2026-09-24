FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Se usa el venv directo (no `uv run`): uv run vuelve a sincronizar
# dependencias en cada arranque, lo que agrega segundos al cold start de
# Cloud Run y requiere salida a internet.
ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000

# Cloud Run inyecta PORT (8080 por defecto); en local cae a 8000.
# Migraciones: mismo imagen con el comando `alembic upgrade head`
# (ver docs/deploy-cloud-run.md).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
