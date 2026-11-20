FROM python:3.13-slim

WORKDIR /app
COPY collector.py /app/collector.py

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CHECKMATE_STATS_DB=/data/stats.sqlite3

RUN useradd --uid 10001 --create-home stats \
    && mkdir -p /data \
    && chown stats:stats /data

USER stats
EXPOSE 8099
CMD ["python", "collector.py"]
