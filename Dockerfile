FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN python -m pip install --upgrade pip setuptools wheel \
    && if [ -f pyproject.toml ]; then pip install -e .; \
       elif [ -f setup.py ]; then pip install -e .; \
       elif [ -f requirements.txt ]; then pip install -r requirements.txt; \
       fi

CMD ["python", "-m", "autonomous_investment_robot", "live-readonly", "--config", "config.kraken_spot.readonly_analysis.yaml"]
