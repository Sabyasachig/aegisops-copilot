FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential curl \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
  && pip install -e .

EXPOSE 4001

CMD ["uvicorn", "aegisops_api.main:app", "--host", "0.0.0.0", "--port", "4001"]
