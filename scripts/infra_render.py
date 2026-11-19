"""Single source for how services are launched.

Both `infra/compose.yaml` (local and production server) and the Runpod pod start script are
rendered from `config/engines.yaml`, `config/models.yaml` and `config/infra.yaml`, so the two
deployments cannot drift apart. `tests/test_infra_render.py` fails if the committed compose file
is out of date; regenerate with `make compose`.

Usage:
    python scripts/infra_render.py compose            # writes infra/compose.yaml
    python scripts/infra_render.py pod-script vllm qwen3.8-27b [--download]
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.settings import load_engines, load_models  # noqa: E402

SECRET_TOKEN = "$LLM_API_KEY"
COMPOSE_PATH = ROOT / "infra" / "compose.yaml"


def load_infra(config_dir: Path = ROOT / "config") -> dict[str, Any]:
    return yaml.safe_load((config_dir / "infra.yaml").read_text(encoding="utf-8"))


def load_embedding_server(config_dir: Path = ROOT / "config") -> dict[str, Any]:
    raw = yaml.safe_load((config_dir / "engines.yaml").read_text(encoding="utf-8"))
    return raw["embedding_server"]


def _fill(template: list[str], values: dict[str, Any]) -> list[str]:
    return [part if part == SECRET_TOKEN else part.format(**values) for part in template]


def engine_argv(engine_key: str, model_key: str, config_dir: Path = ROOT / "config") -> list[str]:
    engine = load_engines(config_dir)[engine_key]
    model = load_models(config_dir)[model_key]
    infra = load_infra(config_dir)
    argv = _fill(
        engine.command,
        {
            "model": model.repo_id,
            "served_name": model.served_name,
            "context_length": model.context_length,
            "max_num_seqs": model.max_num_seqs,
            "port": engine.port,
            "gpu_memory_utilization": infra["gpu_memory"]["llm"],
        },
    )
    return argv + list(model.engine_args.get(engine_key, []))


def embedding_argv(config_dir: Path = ROOT / "config") -> list[str]:
    emb = load_embedding_server(config_dir)
    infra = load_infra(config_dir)
    return _fill(
        emb["command"],
        {
            "model": emb["model"],
            "served_name": emb["served_name"],
            "port": emb["port"],
            "gpu_memory_utilization": infra["gpu_memory"]["embedding"],
        },
    )


def shell_line(argv: list[str]) -> str:
    """Shell command line; the API key is expanded at run time, never written into config."""
    return " ".join('"$LLM_API_KEY"' if a == SECRET_TOKEN else shlex.quote(a) for a in argv)


# Compose -----------------------------------------------------------------------------------


def render_compose(config_dir: Path = ROOT / "config") -> str:
    engines = load_engines(config_dir)
    infra = load_infra(config_dir)
    emb = load_embedding_server(config_dir)
    runtime = yaml.safe_load((config_dir / "runtime.yaml").read_text(encoding="utf-8"))
    default_model = runtime["llm"]["model"]
    pg = infra["postgres"]

    gpu = {
        "resources": {
            "reservations": {
                "devices": [{"driver": "nvidia", "count": "all", "capabilities": ["gpu"]}]
            }
        }
    }
    common_env = {
        "LLM_API_KEY": "${LLM_API_KEY:?LLM_API_KEY .env dosyasında tanımlı olmalı}",
        "HF_HOME": "/models/hf",
        "HF_HUB_OFFLINE": "${HF_HUB_OFFLINE:-1}",
    }

    def gpu_service(image: str, argv: list[str], port: int, health: str) -> dict[str, Any]:
        return {
            "image": image,
            "entrypoint": ["/bin/sh", "-c"],
            "command": ["exec " + shell_line(argv).replace("$", "$$")],
            "environment": dict(common_env),
            "volumes": ["${MODELS_DIR:-./models}:/models"],
            "ports": [f"{port}:{port}"],
            "ipc": "host",
            "deploy": gpu,
            "healthcheck": {
                "test": [
                    "CMD",
                    "python3",
                    "-c",
                    f"import urllib.request; urllib.request.urlopen("
                    f"'http://localhost:{port}{health}', timeout=5)",
                ],
                "interval": "15s",
                "timeout": "10s",
                "retries": 3,
                "start_period": "600s",
            },
            "restart": "unless-stopped",
        }

    services: dict[str, Any] = {}
    for key in sorted(engines):
        e = engines[key]
        svc = gpu_service(
            e.image, engine_argv(key, default_model, config_dir), e.port, e.health_path
        )
        svc["profiles"] = [key]
        services[key] = svc
    services["embedding"] = gpu_service(
        emb["image"], embedding_argv(config_dir), emb["port"], "/health"
    )
    services["postgres"] = {
        "image": pg["image"],
        "environment": {
            "POSTGRES_DB": pg["db"],
            "POSTGRES_USER": pg["user"],
            "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD .env dosyasında tanımlı olmalı}",
        },
        "volumes": ["pgdata:/var/lib/postgresql", "./initdb:/docker-entrypoint-initdb.d:ro"],
        "ports": [f"{pg['port']}:5432"],
        "healthcheck": {
            "test": ["CMD-SHELL", f"pg_isready -U {pg['user']} -d {pg['db']}"],
            "interval": "5s",
            "timeout": "5s",
            "retries": 12,
        },
        "restart": "unless-stopped",
    }
    doc = {"name": "testmentor", "services": services, "volumes": {"pgdata": {}}}
    header = (
        "# ÜRETİLMİŞ DOSYA, elle düzenleme. Kaynak: config/*.yaml; yeniden üret: make compose\n"
        "# Profiller: vllm | sglang (sunum motoru). embedding ve postgres her profilde çalışır.\n"
        "# Etkin model config/runtime.yaml'daki varsayılandır; başka model için make compose\n"
        "# öncesi runtime.yaml'ı değiştir.\n"
    )
    return header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000)


def download_lines(config_dir: Path = ROOT / "config") -> list[str]:
    """Download every candidate model and the embedding model into the HF cache on the volume."""
    models = load_models(config_dir)
    emb = load_embedding_server(config_dir)
    repos = sorted({m.repo_id for m in models.values()} | {emb["model"]})
    return [
        "export HF_HUB_OFFLINE=0 HF_XET_HIGH_PERFORMANCE=1",
        "python3 - <<'PY'",
        "import os, time",
        "from huggingface_hub import snapshot_download",
        f"for repo in {repos!r}:",
        "    t = time.time()",
        "    snapshot_download(repo, token=os.environ.get('HF_TOKEN') or None, max_workers=16)",
        "    print(f'[download] {repo} {time.time() - t:.0f}s', flush=True)",
        "PY",
        "du -sh $HF_HOME/hub/* || true",
    ]


def render_download_script(config_dir: Path = ROOT / "config") -> str:
    """Entrypoint of the CPU download pod: fetch weights, report, then idle until deleted."""
    infra = load_infra(config_dir)
    hf_home = infra["paths"]["hf_home"]
    lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        f"export HF_HOME={hf_home}",
        f"mkdir -p {hf_home}",
        "pip install -q --root-user-action=ignore 'huggingface_hub[hf_xet]'",
        'echo "[download] start $(date -u +%FT%TZ)"',
        *download_lines(config_dir),
        "df -h $HF_HOME || true",
        'echo "[download] DONE $(date -u +%FT%TZ)"',
        "sleep infinity",
    ]
    return "\n".join(lines) + "\n"


# Runpod pod start script --------------------------------------------------------------------


def render_pod_script(
    engine_key: str,
    model_key: str,
    *,
    download: bool = False,
    config_dir: Path = ROOT / "config",
) -> str:
    """Bash script that runs as the pod's entrypoint (one container, no Docker inside)."""
    infra = load_infra(config_dir)
    pg = infra["postgres"]
    hf_home = infra["paths"]["hf_home"]
    mount = infra["runpod"]["volume"]["mount_path"]
    lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        f"export HF_HOME={hf_home}",
        f"mkdir -p {hf_home} {mount}/logs",
        f"LOG={mount}/logs/$(date -u +%Y%m%dT%H%M%SZ)-{engine_key}-{model_key}",
        'mkdir -p "$LOG"',
        'echo "[start] $(date -u +%FT%TZ)"',
    ]
    if download:
        lines += download_lines(config_dir)
    # From here on nothing may be downloaded: a recreated pod must start from the volume.
    lines.append("export HF_HUB_OFFLINE=1")
    if infra["runpod"].get("postgres_mode") == "in_gpu_pod":
        port, user, db = pg["port"], pg["user"], pg["db"]
        lines += [
            "(",
            "  set -e",
            "  export DEBIAN_FRONTEND=noninteractive",
            # PGDG repo: same major version and pgvector package on Ubuntu 22.04 and 24.04.
            "  apt-get update -qq && apt-get install -y -qq postgresql-common gnupg curl ca-certificates lsb-release >/dev/null",
            "  /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y >/dev/null",
            f"  V={pg['major']}",
            "  mkdir -p /etc/postgresql-common/createcluster.d",
            "  echo 'create_main_cluster = false' > /etc/postgresql-common/createcluster.d/no-main.conf",
            "  apt-get install -y -qq postgresql-$V postgresql-$V-pgvector >/dev/null",
            "  BIN=/usr/lib/postgresql/$V/bin",
            f"  PGDATA={mount}/pgdata/$V",
            "  mkdir -p $PGDATA $LOG/pg && chown -R postgres:postgres $(dirname $PGDATA) $LOG/pg",
            "  chmod 700 $PGDATA",
            "  if [ ! -f $PGDATA/PG_VERSION ]; then",
            "    install -o postgres -m 600 /dev/null /tmp/pgpw",
            "    printf '%s' \"$POSTGRES_PASSWORD\" > /tmp/pgpw",
            '    su postgres -s /bin/bash -c "$BIN/initdb -D $PGDATA -A scram-sha-256'
            ' --pwfile=/tmp/pgpw"',
            "    rm -f /tmp/pgpw",
            "    echo 'host all all 0.0.0.0/0 scram-sha-256' >> $PGDATA/pg_hba.conf",
            "  fi",
            '  su postgres -s /bin/bash -c "$BIN/pg_ctl -D $PGDATA -l $LOG/pg/postgres.log'
            f' -o \\"-c listen_addresses=* -p {port}\\" -w start"',
            '  export PGPASSWORD="$POSTGRES_PASSWORD"',
            f'  PSQL="psql -h 127.0.0.1 -p {port} -U postgres -v ON_ERROR_STOP=1"',
            f"  $PSQL -tc \"SELECT 1 FROM pg_roles WHERE rolname='{user}'\" | grep -q 1 ||"
            f" $PSQL -c \"CREATE ROLE {user} LOGIN PASSWORD '$POSTGRES_PASSWORD'\"",
            f"  $PSQL -tc \"SELECT 1 FROM pg_database WHERE datname='{db}'\" | grep -q 1 ||"
            f' $PSQL -c "CREATE DATABASE {db} OWNER {user}"',
            f"  $PSQL -d {db} -c 'CREATE EXTENSION IF NOT EXISTS vector'",
            '  echo "[postgres] ready $(date -u +%FT%TZ)"',
            ') > "$LOG/postgres-setup.log" 2>&1 &',
        ]
    if engine_key == "vllm":
        # The embedding server needs the vLLM runtime; on the SGLang image it is not started.
        lines += [
            f'{shell_line(embedding_argv(config_dir))} > "$LOG/embedding.log" 2>&1 &',
        ]
    lines += [
        'echo "[llm] starting $(date -u +%FT%TZ)"',
        f'{shell_line(engine_argv(engine_key, model_key, config_dir))} 2>&1 | tee "$LOG/llm.log"',
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("compose")
    p = sub.add_parser("pod-script")
    p.add_argument("engine")
    p.add_argument("model")
    p.add_argument("--download", action="store_true")
    args = ap.parse_args()
    if args.cmd == "compose":
        COMPOSE_PATH.write_text(render_compose(), encoding="utf-8")
        print(f"yazıldı: {COMPOSE_PATH.relative_to(ROOT)}")
    else:
        sys.stdout.write(render_pod_script(args.engine, args.model, download=args.download))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
