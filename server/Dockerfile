# Образ серверної частини «Оберіг» (ЛБ5).
# Етап 1 збирає залежності у віртуальне середовище, етап 2 містить лише
# середовище й код і працює від користувача без привілеїв.

FROM python:3.13-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    BACKUP_DIR=/data/backups \
    CA_DIR=/data/ca
RUN groupadd --system oberih \
    && useradd --system --gid oberih --home-dir /app --no-create-home oberih \
    && mkdir -p /data/backups /data/ca \
    && chown -R oberih:oberih /data
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=oberih:oberih alembic.ini ./
COPY --chown=oberih:oberih alembic ./alembic
COPY --chown=oberih:oberih app ./app
COPY --chown=oberih:oberih scripts ./scripts
USER oberih
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"]
# Заголовки X-Forwarded-* приймаються лише від Nginx: порт api не
# публікується назовні, до нього має доступ тільки мережа compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*", "--no-server-header"]
