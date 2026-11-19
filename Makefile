# testmentor paket 0 komutları. Ayarlar config/ altındadır.
# Motor/model seçimi: config/runtime.yaml ya da ENGINE=sglang MODEL=gemma-4-31b make up
SHELL := /bin/bash
ENV := set -a; [ -f .env ] && . ./.env; set +a;
PY := uv run python
UP_ARGS := $(if $(ENGINE),--engine $(ENGINE)) $(if $(MODEL),--model $(MODEL))

.PHONY: up down smoke test lint compose volume download status balance local-up local-down

up:            ## Runpod'da GPU pod'unu aç ve servisler hazır olana kadar bekle
	$(ENV) $(PY) scripts/runpod.py up $(UP_ARGS) && $(PY) scripts/runpod.py wait

down:          ## Pod'u sil, 404 ile doğrula, süre x fiyatı yaz (volume kalır)
	$(ENV) $(PY) scripts/runpod.py down

smoke:         ## 16 eşzamanlı şemaya bağlı istek + önek cache ölçümü
	$(ENV) $(PY) scripts/smoke.py

test:          ## Birim testleri (model çağrısı yok)
	uv run pytest -q --tb=short

lint:
	uv run ruff check . && uv run ruff format --check .

compose:       ## infra/compose.yaml dosyasını config/ altından yeniden üret
	$(PY) scripts/infra_render.py compose

volume:        ## Network volume'u oluştur (yoksa; ücretli)
	$(ENV) $(PY) scripts/runpod.py volume

download:      ## Pod'u indirme kipinde aç: tüm aday ağırlıkları volume'a indirir, sonra sunar
	$(ENV) $(PY) scripts/runpod.py up $(UP_ARGS) --download && $(PY) scripts/runpod.py wait --timeout 5400

status:
	$(ENV) $(PY) scripts/runpod.py status

balance:
	$(ENV) $(PY) scripts/runpod.py balance

local-up:      ## Yerel/üretim sunucusu: docker compose (ENGINE=vllm|sglang)
	docker compose -f infra/compose.yaml --env-file .env --profile $(or $(ENGINE),vllm) up -d --wait

local-down:
	docker compose -f infra/compose.yaml --env-file .env --profile $(or $(ENGINE),vllm) down
