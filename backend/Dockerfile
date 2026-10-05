FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/data/hf \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=600 PIP_RETRIES=10
WORKDIR /app
RUN sed -i 's|http://deb.debian.org|https://cdn-aws.deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get -o Acquire::Retries=5 update && \
    apt-get install -y --no-install-recommends build-essential libgomp1 && \
    rm -rf /var/lib/apt/lists/*
# Dependencies first (cached layer). CPU-only torch so sentence-transformers does not pull the CUDA build.
# The [dev] extras (pytest, ruff) are small and let you run the checks inside the container.
COPY pyproject.toml .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -e ".[dev]"
COPY . .
RUN pip install --no-deps -e .
# Run as an unprivileged user. /data is created here so a new named volume inherits this ownership.
RUN useradd --create-home --uid 1000 ekcode && mkdir -p /data && chown -R ekcode:ekcode /app /data
USER ekcode
