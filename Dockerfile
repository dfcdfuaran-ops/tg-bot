FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder

WORKDIR /opt/remnashop

COPY pyproject.toml uv.lock ./

RUN uv sync --no-dev --no-cache --compile-bytecode \
    && find .venv -type d -name "__pycache__" -exec rm -rf {} + \
    && rm -rf .venv/lib/python3.12/site-packages/pip* \
    && rm -rf .venv/lib/python3.12/site-packages/setuptools* \
    && rm -rf .venv/lib/python3.12/site-packages/wheel*

FROM python:3.12-alpine AS final

WORKDIR /opt/remnashop

ARG BUILD_TIME
ARG BUILD_BRANCH
ARG BUILD_COMMIT
ARG BUILD_TAG

ENV BUILD_TIME=${BUILD_TIME}
ENV BUILD_BRANCH=${BUILD_BRANCH}
ENV BUILD_COMMIT=${BUILD_COMMIT}
ENV BUILD_TAG=${BUILD_TAG}

# Установляем postgresql-client для pg_dump
RUN apk add --no-cache postgresql-client

COPY --from=builder /opt/remnashop/.venv /opt/remnashop/.venv

ENV PATH="/opt/remnashop/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/opt/remnashop

COPY ./src ./src
COPY ./assets /opt/remnashop/assets.default
COPY ./scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
COPY ./scripts/docker-entrypoint-worker.sh ./scripts/docker-entrypoint-worker.sh
COPY ./scripts/docker-entrypoint-scheduler.sh ./scripts/docker-entrypoint-scheduler.sh

RUN chmod +x ./scripts/docker-entrypoint.sh \
    && chmod +x ./scripts/docker-entrypoint-worker.sh \
    && chmod +x ./scripts/docker-entrypoint-scheduler.sh

CMD ["./scripts/docker-entrypoint.sh"]
