FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    CHECKPOINT_PATH=/app/models/model.bin \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY --chown=appuser:appuser code ./code
COPY --chown=appuser:appuser .streamlit ./.streamlit
COPY --chown=appuser:appuser README.md ./README.md

RUN mkdir -p /app/models /app/.cache/huggingface \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl --fail http://localhost:7860/_stcore/health || exit 1

ENTRYPOINT ["python", "code/bootstrap.py"]
