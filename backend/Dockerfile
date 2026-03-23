FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
EXPOSE 8080

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY automation ./automation
COPY backend ./backend

ENV PATH="/app/.venv/bin:$PATH"

CMD ["sh", "-c", "uvicorn backend.app.asgi:app --host 0.0.0.0 --port ${PORT:-8080}"]
