# Phase 3 F12 — VPS Relay image (slim).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 최소 deps — fastapi + uvicorn 만
RUN pip install --no-cache-dir fastapi==0.115.* uvicorn[standard]==0.32.*

COPY relay.py ./

EXPOSE 8765

CMD ["uvicorn", "relay:app", "--host", "0.0.0.0", "--port", "8765"]
