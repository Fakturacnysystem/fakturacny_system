FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY cli ./cli
COPY scripts ./scripts
COPY config*.yaml ./

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
RUN chmod +x scripts/*.sh scripts/*.py || true

CMD ["python", "-m", "cli.run", "--config", "config.kraken_spot.live_profit.yaml", "--nonstop"]
