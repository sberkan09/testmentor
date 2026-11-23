# syntax=docker/dockerfile:1
# testmentor uygulama imajı (paket 10): FastAPI sunucusu ve derlenmiş ön yüz tek imajda.
# Bağlam deponun kökü: docker compose -f infra/compose.yaml build app (ya da make app-image).
#
# Kurum ağında TLS'i yeniden imzalayan bir vekil varsa vekilin kök sertifikası derlemeye gizli
# olarak verilir (imaja girmez), npm ve uv ona güvenir:
#   docker build --secret id=extra_ca,src=/yol/kurum-ca.pem -f infra/app.Dockerfile -t testmentor-app:local .

FROM node:22-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm ci --no-audit --no-fund
COPY api/schema.json /src/api/schema.json
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev --no-install-project
COPY config/ config/
COPY core/ core/
COPY services/ services/
COPY worker/ worker/
COPY api/ api/
COPY --from=web /src/web/dist web/dist
ENV PATH=/app/.venv/bin:$PATH
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
