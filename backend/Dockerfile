FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-cache-dir .

EXPOSE 8000

# Migrations run on every start (idempotent), so the image is
# self-provisioning: `docker compose up` yields a fully migrated database
# with no host-side `alembic upgrade head` step.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
