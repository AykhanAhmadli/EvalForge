FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/src backend/src
COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/alembic.ini
COPY worker/pyproject.toml worker/pyproject.toml
COPY worker/src worker/src

RUN python -m pip install --upgrade pip \
  && python -m pip install --no-cache-dir -e backend -e worker

CMD ["python", "-m", "evalforge_worker.main"]
