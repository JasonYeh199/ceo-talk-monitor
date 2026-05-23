FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY src ./src
COPY main.py config.yaml ./

RUN pip install -r requirements.txt && pip install -e .

EXPOSE 8000

CMD ["uvicorn", "ceo_talk_monitor.api:app", "--host", "0.0.0.0", "--port", "8000"]

