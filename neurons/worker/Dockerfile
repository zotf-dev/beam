# Build from repository root (beam), not from this directory:
#
#   docker build -f neurons/worker/Dockerfile -t beam-worker:latest .
#

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY beam /app/beam/
COPY neurons /app/neurons/

# Worker: worker.py documente bittensor >= 6.0.0 ; le paquet racine exige >= 7.0.0 (pyproject.toml).
# On reste sur la série 7–9 (excl. 10+) : mêmes APIs que le worker (bt.wallet.add_args, bt.config, etc.).
# async-substrate-interface 2.x apporte cyscale en conflit avec scalecodec ; on garde la branche 1.x.
RUN printf "async-substrate-interface>=1.5.6,<2\n" > /tmp/pip-constraints.txt \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && pip install --no-cache-dir -c /tmp/pip-constraints.txt --upgrade "bittensor>=7.0.0,<10" \
    && python -c "import bittensor as bt; v=bt.__version__; print('bittensor OK', v)"

WORKDIR /app/neurons/worker

ENTRYPOINT ["python", "worker.py"]
CMD ["--subtensor.network", "test"]
