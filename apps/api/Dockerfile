FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml constraints.txt ./
COPY config ./config
COPY modules ./modules
COPY manage.py ./

RUN python -m pip install --upgrade pip && \
    python -m pip install -c constraints.txt .

RUN mkdir -p /app/var/private-media && \
    useradd --create-home --uid 10001 app && \
    chown -R app:app /app

USER app

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
