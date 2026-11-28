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


OVERRIDABLE = ("context_length", "max_num_seqs", "gpu_memory_utilization")


def engine_argv(
    engine_key: str,
    model_key: str,
    config_dir: Path = ROOT / "config",
    overrides: dict[str, Any] | None = None,
) -> list[str]:
    """Engine command line. `overrides` changes server settings for one experiment (D5)
    without editing config: context_length, max_num_seqs, gpu_memory_utilization,
    extra_args (list appended at the end)."""
    overrides = dict(overrides or {})
    unknown = set(overrides) - set(OVERRIDABLE) - {"extra_args"}
    if unknown:
        raise ValueError(f"unknown overrides: {sorted(unknown)}")
    engine = load_engines(config_dir)[engine_key]
    if engine.external:
        raise ValueError(f"{engine_key} is an external engine: this project does not launch it")
    model = load_models(config_dir)[model_key]
    infra = load_infra(config_dir)
    values = {
        "model": model.repo_id,
        "served_name": model.served_name,
        "context_length": model.context_length,
        "max_num_seqs": model.max_num_seqs,
        "port": engine.port,
        "gpu_memory_utilization": model.gpu_memory_utilization or infra["gpu_memory"]["llm"],
    }
    values |= {k: overrides[k] for k in OVERRIDABLE if k in overrides}
    argv = _fill(engine.command, values)
    return (
        argv + list(model.engine_args.get(engine_key, [])) + list(overrides.get("extra_args", []))
    )


def embedding_argv(
    config_dir: Path = ROOT / "config", gpu_memory_utilization: Any = None
) -> list[str]:
    emb = load_embedding_server(config_dir)
    infra = load_infra(config_dir)
    return _fill(
        emb["command"],
        {
            "model": emb["model"],
            "served_name": emb["served_name"],
            "port": emb["port"],
            "gpu_memory_utilization": gpu_memory_utilization
            if gpu_memory_utilization is not None
            else infra["gpu_memory"]["embedding"],
        },
    )


def shell_line(argv: list[str]) -> str:
    """Shell command line; the API key is expanded at run time, never written into config."""
    return " ".join('"$LLM_API_KEY"' if a == SECRET_TOKEN else shlex.quote(a) for a in argv)


# Compose -----------------------------------------------------------------------------------


def _sized(argv_with_markers: list[str], line: str, defaults: dict[str, Any], names: dict) -> str:
    """Puts `${NAME:-default}` (Compose interpolation) where the sizing markers are."""
    for key, name in names.items():
        line = line.replace(f"@@{key}@@", f"${{{name}:-{defaults[key]}}}")
    return line


def render_compose(config_dir: Path = ROOT / "config", bundle: dict[str, str] | None = None) -> str:
    """Compose file. `bundle` (paket 12, internetsiz kurulum): `{"app_image": tag}` renders the
    file of the offline bundle: no build, `pull_policy: never`, paths next to the file (config/,
    initdb/, data/, models/), app settings mounted from config/."""
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
    offline = infra["offline"]
    common_env = {
        "LLM_API_KEY": "${LLM_API_KEY:?LLM_API_KEY .env dosyasında tanımlı olmalı}",
        "HF_HOME": "/models/hf",
        # paket 12: nothing is downloaded and no telemetry is sent (offline.env in infra.yaml)
        **{k: f"${{{k}:-{v}}}" for k, v in offline["env"].items()},
    }

    def gpu_service(
        image: str,
        argv: list[str],
        port: int,
        health: str,
        sizing: tuple[dict[str, Any], dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        line = "exec " + shell_line(argv).replace("$", "$$")
        if sizing is not None:
            line = _sized(argv, line, *sizing)
        return {
            "image": image,
            "entrypoint": ["/bin/sh", "-c"],
            "command": [line],
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
    model = load_models(config_dir)[default_model]
    names = dict(offline["sizing_env"])
    defaults = {
        "context_length": model.context_length,
        "max_num_seqs": model.max_num_seqs,
        "gpu_memory_utilization": model.gpu_memory_utilization or infra["gpu_memory"]["llm"],
    }
    markers = {k: f"@@{k}@@" for k in names}
    for key in sorted(k for k in engines if not engines[k].external):
        e = engines[key]
        svc = gpu_service(
            e.image,
            engine_argv(key, default_model, config_dir, overrides=markers),
            e.port,
            e.health_path,
            sizing=(defaults, names),
        )
        svc["profiles"] = [key]
        services[key] = svc
    app = infra["app"]
    for key in sorted(k for k in engines if not engines[k].external):
        services[key]["networks"] = {"default": {"aliases": [app["llm_alias"]]}}
    services["embedding"] = gpu_service(
        emb["image"],
        embedding_argv(config_dir, gpu_memory_utilization="@@gpu_memory_utilization@@"),
        emb["port"],
        "/health",
        sizing=(
            {"gpu_memory_utilization": infra["gpu_memory"]["embedding"]},
            {"gpu_memory_utilization": offline["embedding_memory_env"]},
        ),
    )
    # Every engine profile, not the external one: there the embedding server is elsewhere.
    services["embedding"]["profiles"] = sorted(k for k in engines if not engines[k].external)
    services["postgres"] = {
        "image": pg["image"],
        "environment": {
            "POSTGRES_DB": pg["db"],
            "POSTGRES_USER": pg["user"],
            "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD .env dosyasında tanımlı olmalı}",
        },
        "volumes": ["pgdata:/var/lib/postgresql", "./initdb:/docker-entrypoint-initdb.d:ro"],
        "ports": [f"${{POSTGRES_PORT:-{pg['port']}}}:5432"],
        "healthcheck": {
            "test": ["CMD-SHELL", f"pg_isready -U {pg['user']} -d {pg['db']}"],
            "interval": "5s",
            "timeout": "5s",
            "retries": 12,
        },
        "restart": "unless-stopped",
    }
    services["app"] = app_service(infra, runtime, emb)
    if bundle is not None:
        app_svc = services["app"]
        app_svc.pop("build", None)
        app_svc["image"] = bundle["app_image"]
        app_svc["volumes"] = ["${TESTMENTOR_DATA_DIR:-./data}:/app/data", "./config:/app/config:ro"]
        for svc in services.values():
            svc["pull_policy"] = "never"  # the offline machine has only the loaded images
    doc = {"name": "testmentor", "services": services, "volumes": {"pgdata": {}}}
    profiles = " | ".join(sorted(k for k in engines if not engines[k].external))
    if bundle is not None:
        header = (
            "# İnternetsiz kurulum paketinin Compose dosyası (paket 12). Üretildi: make offline-bundle\n"
            "# İmajlar docker load ile yüklenir, hiçbiri çekilmez (pull_policy: never). Ağırlıklar\n"
            "# ./models/hf altında, uygulama ayarları ./config altında. Kurulum: KURULUM.md\n"
            f"# Profiller: {profiles} (model sunucusu ve embedding ile) | {app['external_profile']}\n"
        )
        return header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000)
    header = (
        "# ÜRETİLMİŞ DOSYA, elle düzenleme. Kaynak: config/*.yaml; yeniden üret: make compose\n"
        f"# Profiller: {profiles} (sunum motoru, embedding ile) | {app['external_profile']}\n"
        "# (model ve embedding kurumun ayrı sunucusunda; adresleri .env'de: LLM_BASE_URL,\n"
        "# EMBEDDING_BASE_URL). postgres ve app her profilde çalışır (docs/pilot.md).\n"
        "# Etkin model config/runtime.yaml'daki varsayılandır; başka model için make compose\n"
        "# öncesi runtime.yaml'ı değiştir.\n"
    )
    return header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000)


def app_service(
    infra: dict[str, Any], runtime: dict[str, Any], emb: dict[str, Any]
) -> dict[str, Any]:
    """API and built frontend (paket 10). Model and embedding addresses default to the services
    of this compose file (engine alias, `embedding`); in the external profile `.env` sets
    LLM_BASE_URL and EMBEDDING_BASE_URL. Secrets come from `.env`, never from config."""
    app, pg = infra["app"], infra["postgres"]
    port = int(app["port"])
    dsn = f"postgresql://{pg['user']}:${{POSTGRES_PASSWORD}}@postgres:5432/{pg['db']}"
    return {
        "image": app["image"],
        "build": {"context": "..", "dockerfile": app["dockerfile"]},
        "environment": {
            "TESTMENTOR_PG_DSN": dsn,
            "TESTMENTOR_AUTH_MODE": f"${{TESTMENTOR_AUTH_MODE:-{app['auth_mode']}}}",
            "TESTMENTOR_AUTH_SECRET": "${TESTMENTOR_AUTH_SECRET:-}",
            "TESTMENTOR_USERS_FILE": "/app/data/users.yaml",
            "TESTMENTOR_FAKE_LLM": "${TESTMENTOR_FAKE_LLM:-0}",
            "LLM_ENGINE": f"${{LLM_ENGINE:-{runtime['llm']['engine']}}}",
            "LLM_MODEL": f"${{LLM_MODEL:-{runtime['llm']['model']}}}",
            "LLM_HOST": app["llm_alias"],
            "LLM_BASE_URL": "${LLM_BASE_URL:-}",
            "EMBEDDING_BASE_URL": f"${{EMBEDDING_BASE_URL:-http://embedding:{emb['port']}/v1}}",
            "LLM_API_KEY": "${LLM_API_KEY:?LLM_API_KEY .env dosyasında tanımlı olmalı}",
        },
        "volumes": [f"${{TESTMENTOR_DATA_DIR:-{app['data_dir']}}}:/app/data"],
        "ports": [f"${{APP_PORT:-{app['host_port']}}}:{port}"],
        "depends_on": {"postgres": {"condition": "service_healthy"}},
        "healthcheck": {
            "test": [
                "CMD",
                "python",
                "-c",
                f"import urllib.request; urllib.request.urlopen("
                f"'http://localhost:{port}/auth/config', timeout=5)",
            ],
            "interval": "10s",
            "timeout": "5s",
            "retries": 6,
            "start_period": "30s",
        },
        "restart": "unless-stopped",
    }


def download_lines(config_dir: Path = ROOT / "config", clean: list[str] | None = None) -> list[str]:
    """Download every candidate model and the embedding model into the HF cache on the volume.

    `clean` lists repo ids whose cache directory is removed first (one-off repair after a
    download that pulled files now listed in `download_ignore`).
    """
    models = load_models(config_dir)
    emb = load_embedding_server(config_dir)
    plan = {m.repo_id: list(m.download_ignore) for m in models.values()}
    plan.setdefault(emb["model"], [])
    plan = dict(sorted(plan.items()))
    lines = [
        # Xet chunk cache on the container disk, not on the volume.
        "export HF_HUB_OFFLINE=0 HF_XET_CACHE=/tmp/xet-cache",
    ]
    if clean:
        lines.append('rm -rf "$HF_HOME/xet"')  # old chunk cache from an earlier run, if any
    for repo in sorted(clean or []):
        lines.append(f'rm -rf "$HF_HOME/hub/models--{repo.replace("/", "--")}"')
    lines += [
        "python3 - <<'PY'",
        "import os, time",
        "from huggingface_hub import snapshot_download",
        f"plan = {plan!r}",
        "for repo, ignore in plan.items():",
        "    t = time.time()",
        "    snapshot_download(repo, token=os.environ.get('HF_TOKEN') or None, max_workers=16,",
        "                      ignore_patterns=ignore or None)",
        "    print(f'[download] {repo} {time.time() - t:.0f}s', flush=True)",
        "PY",
        "du -sh $HF_HOME/hub/* || true",
    ]
    return lines


def render_download_script(
    config_dir: Path = ROOT / "config", clean: list[str] | None = None
) -> str:
    """Entrypoint of the CPU download pod: fetch weights, report, then idle until deleted."""
    infra = load_infra(config_dir)
    hf_home = infra["paths"]["hf_home"]
    lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        f"export HF_HOME={hf_home}",
        f"mkdir -p {hf_home}",
        *watchdog_lines(config_dir, log="/proc/1/fd/1"),
        "pip install -q --root-user-action=ignore 'huggingface_hub[hf_xet]'",
        'echo "[download] start $(date -u +%FT%TZ)"',
        # A failure must not end the container: Runpod would restart it and loop the download.
        "trap 'echo \"[download] FAILED $(date -u +%FT%TZ)\"; df -h $HF_HOME || true; sleep infinity' ERR",
        *download_lines(config_dir, clean),
        "df -h $HF_HOME || true",
        'echo "[download] DONE $(date -u +%FT%TZ)"',
        'self_delete "indirme bitti"',
        "sleep infinity",
    ]
    return "\n".join(lines) + "\n"


# Credit protection ------------------------------------------------------------------------

SELF_DELETE_PY = """import os, sys, urllib.request
pid, key = os.environ.get("RUNPOD_POD_ID", ""), os.environ.get("RUNPOD_API_KEY", "")
for url in (f"https://api.runpod.io/v2/pods/{pid}", f"https://rest.runpod.io/v1/pods/{pid}"):
    try:
        req = urllib.request.Request(url, method="DELETE", headers={"Authorization": f"Bearer {key}"})
        print("[watchdog] DELETE", url, urllib.request.urlopen(req, timeout=30).status, flush=True)
        sys.exit(0)
    except Exception as exc:
        print("[watchdog] DELETE", url, "failed:", getattr(exc, "code", ""), str(exc)[:200], flush=True)
sys.exit(1)
"""


def watchdog_lines(
    config_dir: Path = ROOT / "config",
    log: str = "/tmp/watchdog.log",
    interval_s: int = 60,
    settings: dict[str, Any] | None = None,
) -> list[str]:
    """Background loop that deletes the pod itself (Runpod injects RUNPOD_POD_ID and a
    pod-scoped RUNPOD_API_KEY into every pod; verified 20 Nov 2026). Triggers:
    - the absolute deadline (WATCHDOG_DEADLINE epoch, or /tmp/watchdog_deadline if extended);
    - the GPU idle for idle_minutes after a grace period (pods without GPU: deadline only).
    It does not depend on the controlling session being alive."""
    wd = settings or load_infra(config_dir)["watchdog"]
    idle, grace, below = (
        int(wd["idle_minutes"]),
        int(wd["grace_minutes"]),
        int(wd["gpu_util_idle_below"]),
    )
    return [
        "self_delete() {",
        '  echo "[watchdog] $1; pod siliniyor $(date -u +%FT%TZ)"',
        "  until python3 - <<'PYDEL'",
        SELF_DELETE_PY.rstrip("\n"),
        "PYDEL",
        "  do sleep 30; done",
        "}",
        "(",
        "  set +e",
        "  start=$(date +%s); idle=0",
        '  echo "[watchdog] başladı; son tarih ${WATCHDOG_DEADLINE:-yok}, boşta sınırı '
        f'{idle} dk (ilk {grace} dk sayılmaz)"',
        f"  while sleep {interval_s}; do",
        "    now=$(date +%s)",
        '    deadline=$(cat /tmp/watchdog_deadline 2>/dev/null || echo "${WATCHDOG_DEADLINE:-0}")',
        '    if [ "${deadline:-0}" -gt 0 ] && [ "$now" -ge "$deadline" ]; then',
        '      self_delete "en uzun ömür doldu"; continue',
        "    fi",
        f"    if command -v nvidia-smi >/dev/null && [ $((now - start)) -ge {grace * interval_s} ]; then",
        "      util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -1 | tr -dc 0-9)",
        f'      if [ "${{util:-0}}" -lt {below} ]; then idle=$((idle + 1)); else idle=0; fi',
        f'      if [ "$idle" -ge {idle} ]; then self_delete "GPU {idle} dk boşta"; fi',
        "    fi",
        "  done",
        f") >> {log} 2>&1 &",
    ]


# Runpod pod start script --------------------------------------------------------------------


def render_pod_script(
    engine_key: str,
    model_key: str,
    *,
    download: bool = False,
    config_dir: Path = ROOT / "config",
    overrides: dict[str, Any] | None = None,
    offline_rehearsal: bool = False,
) -> str:
    """Bash script that runs as the pod's entrypoint (one container, no Docker inside).

    `offline_rehearsal` (paket 12): the model and embedding servers run with every HTTP(S)
    proxy variable pointing at a dead address, so whatever they try to fetch fails; the
    watchdog (started before, without them) keeps its own network to delete the pod. The
    model revisions in the cache are printed (`[refs]`) and the embedding log goes to stdout."""
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
        *watchdog_lines(config_dir, log='"$LOG/watchdog.log"'),
    ]
    if download:
        lines += download_lines(config_dir)
    # From here on nothing may be downloaded: a recreated pod must start from the volume.
    offline = infra["offline"]
    lines.append("export " + " ".join(f"{k}={v}" for k, v in offline["env"].items()))
    dead = ""
    if offline_rehearsal:
        proxy = offline["rehearsal_proxy"]
        dead = (
            "env "
            + " ".join(
                f"{k}={proxy}"
                for k in (
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "ALL_PROXY",
                    "http_proxy",
                    "https_proxy",
                    "all_proxy",
                )
            )
            + " NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 "
        )
        lines += [
            'echo "[offline] çevrimdışı prova: model ve embedding süreçlerinin çıkışı ölü vekile"',
            f'for r in {hf_home}/hub/models--*/refs/main; do echo "[refs] $r $(cat "$r")"; done',
        ]
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
            # The network volume (MooseFS) refuses chown, so data lives on the container disk.
            "  PGDATA=/var/lib/postgresql/$V/testmentor",
            "  mkdir -p $PGDATA /var/log/testmentor-pg && chown -R postgres:postgres $PGDATA /var/log/testmentor-pg",
            "  chmod 700 $PGDATA",
            "  if [ ! -f $PGDATA/PG_VERSION ]; then",
            # Not directly in /tmp: with protected_regular, root cannot write a file owned by
            # another user in a sticky directory.
            "    PWDIR=$(mktemp -d) && printf '%s' \"$POSTGRES_PASSWORD\" > $PWDIR/pw",
            "    chown -R postgres $PWDIR && chmod 700 $PWDIR",
            '    su postgres -s /bin/bash -c "$BIN/initdb -D $PGDATA -A scram-sha-256 --pwfile=$PWDIR/pw"',
            "    rm -rf $PWDIR",
            "    echo 'host all all 0.0.0.0/0 scram-sha-256' >> $PGDATA/pg_hba.conf",
            "  fi",
            '  su postgres -s /bin/bash -c "$BIN/pg_ctl -D $PGDATA -l /var/log/testmentor-pg/postgres.log'
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
        emb_out = (
            '2>&1 | sed -u "s/^/[embedding] /" | tee "$LOG/embedding.log" &'
            if offline_rehearsal
            else '> "$LOG/embedding.log" 2>&1 &'
        )
        lines += [
            f"{dead}{shell_line(embedding_argv(config_dir))} {emb_out}",
        ]
    lines += [
        'echo "[llm] starting $(date -u +%FT%TZ)"',
        f'{dead}{shell_line(engine_argv(engine_key, model_key, config_dir, overrides))} 2>&1 | tee "$LOG/llm.log"',
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("compose")
    b = sub.add_parser("compose-bundle", help="internetsiz kurulum paketinin Compose dosyası")
    b.add_argument("--app-image", required=True)
    b.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("pod-script")
    p.add_argument("engine")
    p.add_argument("model")
    p.add_argument("--download", action="store_true")
    args = ap.parse_args()
    if args.cmd == "compose":
        COMPOSE_PATH.write_text(render_compose(), encoding="utf-8")
        print(f"yazıldı: {COMPOSE_PATH.relative_to(ROOT)}")
    elif args.cmd == "compose-bundle":
        args.out.write_text(render_compose(bundle={"app_image": args.app_image}), encoding="utf-8")
        print(f"yazıldı: {args.out}")
    else:
        sys.stdout.write(render_pod_script(args.engine, args.model, download=args.download))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
