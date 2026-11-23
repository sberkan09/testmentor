# testmentor paket 0 komutları. Ayarlar config/ altındadır.
# Motor/model seçimi: config/runtime.yaml ya da ENGINE=sglang MODEL=gemma-4-31b make up
SHELL := /bin/bash
ENV := set -a; [ -f .env ] && . ./.env; set +a;
PY := uv run python
UP_ARGS := $(if $(ENGINE),--engine $(ENGINE)) $(if $(MODEL),--model $(MODEL)) $(foreach o,$(OVERRIDE),--override $(o))
MAX_ARGS := $(if $(MAX_HOURS),--max-hours $(MAX_HOURS))

.PHONY: up down smoke test pg-test lint compose volume download download-down reconfigure extend batch eval judge status balance local-up local-down app-image users-add

up:            ## Runpod'da GPU pod'unu aç ve servisler hazır olana kadar bekle
	$(ENV) $(PY) scripts/runpod.py up $(UP_ARGS) $(MAX_ARGS) && $(PY) scripts/runpod.py wait

down:          ## Pod'u sil, 404 ile doğrula, süre x fiyatı yaz (volume kalır)
	$(ENV) $(PY) scripts/runpod.py down

smoke:         ## 16 eşzamanlı şemaya bağlı istek + önek cache ölçümü
	$(ENV) $(PY) scripts/smoke.py

test:          ## Birim testleri (model çağrısı yok)
	uv run pytest -q --tb=short

pg-test:       ## Postgres depo testleri (geçici küme ya da TESTMENTOR_PG_DSN; sunucu yoksa atlanır)
	uv run pytest -q --tb=short -rs tests/core/test_store_contract.py tests/worker/test_store.py

lint:
	uv run ruff check . && uv run ruff format --check .

compose:       ## infra/compose.yaml dosyasını config/ altından yeniden üret
	$(PY) scripts/infra_render.py compose

volume:        ## Network volume'u oluştur (yoksa; ücretli)
	$(ENV) $(PY) scripts/runpod.py volume

download:      ## Aynı veri merkezinde CPU pod'u açıp tüm aday ağırlıkları volume'a indirir
	$(ENV) $(PY) scripts/runpod.py download

download-down: ## İndirme pod'unu sil (404 ile doğrulanır)
	$(ENV) $(PY) scripts/runpod.py download-down

reconfigure:   ## Açık pod'da model/motor/sunucu ayarını değiştir (imaj yeniden çekilmez)
	$(ENV) $(PY) scripts/runpod.py reconfigure $(UP_ARGS) && $(PY) scripts/runpod.py wait

extend:        ## Pod'un kendini silme süresini uzat: make extend HOURS=1
	$(ENV) $(PY) scripts/runpod.py extend --hours $(HOURS)

batch:         ## Deney grubunu tek pod'da koş, sonunda pod her durumda silinir: make batch BATCH=paket1
	$(ENV) $(PY) -m eval.batch config/batches/$(BATCH).yaml

eval:          ## Deney koş: make eval EXP=d1-vllm
	$(ENV) $(PY) -m eval.run --config config/experiments/$(EXP).yaml

judge:         ## Hakem (katman 2): make judge RUN=results/<koşu>
	$(ENV) $(PY) -m eval.judge $(RUN)

status:
	$(ENV) $(PY) scripts/runpod.py status

balance:
	$(ENV) $(PY) scripts/runpod.py balance

# Compose profili: vllm | sglang (model sunucusu bu makinede) | harici (yalnızca Postgres ve
# uygulama; model ve embedding adresleri .env'de). Kurulum: docs/pilot.md
PROFILE := $(or $(PROFILE),$(ENGINE),vllm)
comma := ,
COMPOSE := docker compose -f infra/compose.yaml --env-file .env --profile $(PROFILE)
COMPOSE_ENV := $(if $(filter-out harici,$(PROFILE)),LLM_ENGINE=$(PROFILE))

local-up:      ## Yerel/üretim sunucusu: docker compose (PROFILE=vllm|sglang|harici)
	$(COMPOSE_ENV) $(COMPOSE) up -d --wait

local-down:
	$(COMPOSE) down

app-image:     ## Uygulama imajı (API + ön yüz); kurum vekili varsa EXTRA_CA=/yol/ca.pem
	docker build $(if $(EXTRA_CA),--secret id=extra_ca$(comma)src=$(EXTRA_CA)) -f infra/app.Dockerfile -t testmentor-app:local .

users-add:     ## Parolalı giriş kullanıcısı ekle (çalışan uygulamada): make users-add NAME=ayse
	$(COMPOSE) exec app python -m api.users add $(NAME)

# Paket 8: ön yüz (web/)
.PHONY: web-install web-build web-test web-e2e

web-install:   ## npm bağımlılıkları (package-lock.json ile)
	cd web && npm ci

web-build:     ## tip üretimi denetimi, tsc ve vite derlemesi (web/dist)
	cd web && npm run build

web-test:      ## vitest birim testleri + lint (arka uç gerekmez)
	cd web && npm run lint && npm test

web-e2e:       ## Playwright uçtan uca testi: TESTMENTOR_FAKE_LLM=1 API + vite önizleme (web/e2e/README.md)
	cd web && npm run e2e
