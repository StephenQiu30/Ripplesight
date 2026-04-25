FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace

WORKDIR /workspace

COPY pyproject.toml README.md /workspace/
COPY backend /workspace/backend
COPY services /workspace/services

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install -e .

CMD ["python", "-V"]
