# ===== Base =====
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg

# Déps système pour psycopg2-binary/matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc libpq-dev \
      libfreetype6 libjpeg62-turbo libpng16-16 \
      libexpat1 libglib2.0-0 libfontconfig1 \
      ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ===== Dépendances =====
# Copie requirements en premier pour profiter du cache Docker
COPY ./requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# ===== Code =====
# On copie uniquement le dossier api (où vivent main.py, services/, routes/, etc.)
COPY . /app/api

# Sécurité: user non-root
RUN useradd -m appuser
USER appuser

# Port exposé par uvicorn
EXPOSE 8080

# CMD par défaut : uvicorn sur notre nouvelle app modulaire
# (si ton compose override "command:", tu n'as rien à changer)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
