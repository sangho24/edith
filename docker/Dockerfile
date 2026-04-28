# Phase 3 F11 — Home Hub Edith image.
# uv 기반 Python 3.12. harness 가 cron으로 daily/morning loop 실행.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    EDITH_HOME=/data/edith

# uv install (rust 기반 — apt 없이 pip로 가능)
RUN pip install --no-cache-dir uv

WORKDIR /app

# 의존성 layer 분리
COPY pyproject.toml ./
RUN uv venv --python 3.12 /opt/venv \
    && /opt/venv/bin/uv pip install -e . --python /opt/venv/bin/python

# harness 코드 복사
COPY harness ./harness
COPY README.md ./

# venv를 PATH에 추가
ENV PATH="/opt/venv/bin:${PATH}"

# 데이터 볼륨 (raw, wiki, harness/traces)
VOLUME ["/data/edith"]

ENTRYPOINT ["python", "-m", "harness.cli"]
CMD ["--help"]
