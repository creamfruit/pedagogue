FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x scripts/*.sh \
    && useradd --create-home --uid 10001 pedagogue \
    && mkdir -p storage \
    && chown -R pedagogue /app

USER pedagogue

EXPOSE 8000

CMD ["scripts/start.sh"]
