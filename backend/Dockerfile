# Backend FastAPI + Celery + Playwright
# Multi-stage para reduzir tamanho da imagem final.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=America/Sao_Paulo

# Dependências do sistema necessárias para:
# - psycopg (libpq) → Postgres
# - cryptography (.pfx → PEM no Integra/SEFAZ)
# - Playwright Chromium (libs gráficas)
# - postgresql-client → pg_dump em backup
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    curl \
    ca-certificates \
    postgresql-client \
    # Libs do Chromium para Playwright
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxkbcommon0 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala deps Python
COPY requirements.txt .
RUN pip install -r requirements.txt

# Instala Chromium do Playwright (uma vez no build).
# NOTA: NÃO chamamos `playwright install-deps` porque ele tenta instalar
# pacotes Ubuntu 20.04 (ttf-unifont, ttf-ubuntu-font-family) que não
# existem em Debian Trixie (base do python:3.12-slim). As libs nativas
# (libnss3, libatk1.0-0, libdrm2, libgbm1, fonts-liberation, ...) já estão
# instaladas via apt-get acima — cobrem 100% do que o Chromium precisa.
RUN playwright install chromium

# Código do app
COPY . .

# Storage e logs (montados como volumes em produção)
RUN mkdir -p /app/storage/xmls /app/storage/cnds /app/storage/sitfis \
             /app/storage/apuracoes /app/storage/reports /app/logs

# Usuário não-root
RUN useradd -m -u 1000 pac && chown -R pac:pac /app
USER pac

EXPOSE 8000

# Default: backend FastAPI. Override no docker-compose para worker/beat.
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
