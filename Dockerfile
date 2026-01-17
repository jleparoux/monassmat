FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV FRONTEND_DIR=/app/frontend

COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src
COPY frontend /app/frontend
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY scripts /app/scripts

RUN pip install --no-cache-dir .[db-postgres]
RUN chmod +x /app/scripts/docker-entrypoint.sh

EXPOSE 8000
CMD ["/app/scripts/docker-entrypoint.sh"]
