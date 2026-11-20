"""Runpod lifecycle for paket 0 (REST v2). One pod runs the engine, the embedding server and
Postgres as processes (Runpod pods cannot run Docker Compose).

    python scripts/runpod.py balance
    python scripts/runpod.py volume             # create the network volume if missing (billable)
    python scripts/runpod.py up [--engine vllm] [--model qwen3.8-27b] [--download]
    python scripts/runpod.py wait               # block until LLM answers; prints seconds
    python scripts/runpod.py status
    python scripts/runpod.py down               # delete the pod, verify 404, print cost

Auth: RUNPOD_API_KEY (Bearer). Only resources recorded in infra/.runpod-state.json are deleted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.infra_render import (  # noqa: E402
    load_embedding_server,
    load_infra,
    render_download_script,
    render_pod_script,
)
from scripts.runpod_state import (  # noqa: E402
    ensure_env_secret,
    proxy_url,
    read_state,
    write_state,
)
from services.settings import load_engines, load_runtime  # noqa: E402

GRAPHQL = "https://api.runpod.io/graphql"


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class Runpod:
    def __init__(self) -> None:
        infra = load_infra()["runpod"]
        self.cfg = infra
        base = os.environ.get("RUNPOD_API_BASE", infra["api_base"]).rstrip("/")
        key = os.environ.get("RUNPOD_API_KEY")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self.http = httpx.Client(base_url=base, headers=headers, timeout=60)
        self.gql = httpx.Client(headers=headers, timeout=30)

    def req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        r = self.http.request(method, path, **kw)
        if r.status_code >= 400 and not (method == "GET" and r.status_code == 404):
            raise SystemExit(f"Runpod {method} {path}: HTTP {r.status_code} {r.text[:1000]}")
        return r

    def balance(self) -> float:
        r = self.gql.post(GRAPHQL, json={"query": "query { myself { clientBalance } }"})
        r.raise_for_status()
        return float(r.json()["data"]["myself"]["clientBalance"])

    def find_volume(self) -> dict[str, Any] | None:
        v = self.cfg["volume"]
        vols = self.req("GET", "/network-volumes").json()["networkVolumes"]
        for vol in vols:
            if vol["name"] == v["name"] and vol["dataCenter"] == self.cfg["data_center"]:
                return vol
        return None

    def create_volume(self) -> dict[str, Any]:
        v = self.cfg["volume"]
        body = {
            "name": v["name"],
            "size": v["size_gb"],
            "dataCenter": self.cfg["data_center"],
            "type": v["type"],
        }
        return self.req("POST", "/network-volumes", json=body).json()

    def create_pod(self, body: dict[str, Any], retries: int = 0, wait_s: float = 30) -> dict:
        """Create a pod; on "no instances available" retry `retries` times (stock is volatile)."""
        for attempt in range(retries + 1):
            r = self.http.post("/pods", json=body)
            if r.status_code < 400:
                return r.json()
            if "no longer any instances available" not in r.text or attempt == retries:
                raise SystemExit(f"Runpod POST /pods: HTTP {r.status_code} {r.text[:1000]}")
            print(f"stok yok, {wait_s:.0f} sn sonra yeniden ({attempt + 1}/{retries})", flush=True)
            time.sleep(wait_s)
        raise AssertionError("unreachable")

    def get_pod(self, pod_id: str) -> httpx.Response:
        return self.req("GET", f"/pods/{pod_id}")

    def delete_pod(self, pod_id: str) -> None:
        r = self.http.delete(f"/pods/{pod_id}")
        if r.status_code not in (200, 202, 204, 404):
            raise SystemExit(f"delete failed: HTTP {r.status_code} {r.text[:500]}")

    def list_pods(self) -> list[dict[str, Any]]:
        return self.req("GET", "/pods").json()["pods"]


def watchdog_deadline(hours: float) -> int:
    """Absolute self-delete time for a new pod. Pods are never opened without one."""
    wd = load_infra()["watchdog"]
    if not wd.get("enabled"):
        raise SystemExit(
            "watchdog kapalı: bekçisiz pod açılmaz (config/infra.yaml watchdog.enabled)"
        )
    if not 0 < float(hours) <= 24:
        raise SystemExit(f"en uzun ömür 0–24 saat olmalı, verilen {hours}")
    return int(time.time() + float(hours) * 3600)


def parse_overrides(items: list[str] | None) -> dict[str, Any]:
    """`key=value` pairs from the command line; numbers become int/float."""
    out: dict[str, Any] = {}
    for item in items or []:
        key, _, value = item.partition("=")
        if key == "extra_args":
            out[key] = value.split()
            continue
        try:
            out[key] = int(value)
        except ValueError:
            out[key] = float(value)
    return out


def pod_body(
    engine_key: str,
    model_key: str,
    volume_id: str,
    download: bool,
    overrides: dict[str, Any] | None = None,
    deadline: int | None = None,
) -> dict[str, Any]:
    cfg = load_infra()["runpod"]
    engine = load_engines()[engine_key]
    emb = load_embedding_server()
    pg_port = load_infra()["postgres"]["port"]
    ports = [f"{engine.port}/http"]
    if engine_key == "vllm":
        ports.append(f"{emb['port']}/http")
    if cfg.get("postgres_mode") == "in_gpu_pod" and cfg.get("postgres_expose_tcp"):
        ports.append(f"{pg_port}/tcp")
    if not deadline:
        raise ValueError("pod needs a watchdog deadline (epoch seconds)")
    env = {
        "LLM_API_KEY": ensure_env_secret("LLM_API_KEY"),
        "POSTGRES_PASSWORD": ensure_env_secret("POSTGRES_PASSWORD"),
        "WATCHDOG_DEADLINE": str(int(deadline)),
    }
    if download:
        env["HF_TOKEN"] = cfg["hf_token_secret"]  # Runpod substitutes the secret at boot
    return {
        "name": f"{cfg['pod_name']}-{engine_key}",
        "image": engine.image,
        "cloud": cfg["cloud"],
        "dataCenterIds": [cfg["data_center"]],
        # minCudaVersion is not sent: with it the API answered "no instances available" while
        # stock existed (19 Nov 2026). The host CUDA version is checked after creation instead.
        "gpu": {"id": cfg["gpu_type_id"], "count": 1},
        "disk": cfg["container_disk_gb"],
        "mounts": {"network": [{"volumeId": volume_id, "path": cfg["volume"]["mount_path"]}]},
        "ports": ports,
        "env": env,
        "entrypoint": [
            "bash",
            "-c",
            render_pod_script(engine_key, model_key, download=download, overrides=overrides),
        ],
    }


def download_body(volume_id: str, clean: list[str] | None = None) -> dict[str, Any]:
    cfg = load_infra()["runpod"]
    d = cfg["download_pod"]
    return {
        "name": d["name"],
        "image": d["image"],
        "cloud": cfg["cloud"],
        "dataCenterIds": [cfg["data_center"]],
        "cpu": {"id": d["cpu_flavor"], "vcpuCount": d["vcpu"]},
        "disk": d["container_disk_gb"],
        "mounts": {"network": [{"volumeId": volume_id, "path": cfg["volume"]["mount_path"]}]},
        "env": {
            "HF_TOKEN": cfg["hf_token_secret"],
            "WATCHDOG_DEADLINE": str(
                watchdog_deadline(load_infra()["watchdog"]["download_max_hours"])
            ),
        },
        "entrypoint": ["bash", "-c", render_download_script(clean=clean)],
    }


def cmd_download(rp: Runpod, args: argparse.Namespace) -> int:
    state = read_state()
    if state.get("download_pod"):
        raise SystemExit(f"kayıtlı indirme pod'u var: {state['download_pod']['id']}")
    vol = rp.find_volume()
    if vol is None:
        raise SystemExit("network volume yok; önce `make volume`")
    pod = rp.create_pod(download_body(vol["id"], args.clean))
    state["download_pod"] = {
        "id": pod["id"],
        "created_at": now(),
        "created_monotonic_hint": time.time(),
        "cost_per_hr": pod.get("cost"),
    }
    write_state(state)
    print(f"indirme pod'u: {pod['id']} ücret={pod.get('cost')} USD/saat")
    return 0


def cmd_download_down(rp: Runpod, _: argparse.Namespace) -> int:
    state = read_state()
    pod = state.get("download_pod")
    if not pod:
        print("kayıtlı indirme pod'u yok")
        return 0
    rp.delete_pod(pod["id"])
    for _ in range(30):
        if rp.get_pod(pod["id"]).status_code == 404:
            break
        time.sleep(2)
    code = rp.get_pod(pod["id"]).status_code
    hours = (time.time() - pod["created_monotonic_hint"]) / 3600
    cost = hours * float(pod.get("cost_per_hr") or 0)
    print(f"silindi: {pod['id']} get-pod HTTP {code}; {hours:.2f} saat, yaklaşık {cost:.2f} USD")
    if code != 404:
        raise SystemExit("indirme pod'u hâlâ görünüyor")
    state.setdefault("history", []).append(
        {
            **pod,
            "kind": "download",
            "deleted_at": now(),
            "hours": round(hours, 3),
            "approx_cost_usd": round(cost, 2),
        }
    )
    state.pop("download_pod")
    write_state(state)
    return 0


def _version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def cmd_balance(rp: Runpod, _: argparse.Namespace) -> int:
    print(f"bakiye: {rp.balance():.2f} USD")
    return 0


def cmd_volume(rp: Runpod, _: argparse.Namespace) -> int:
    vol = rp.find_volume()
    if vol is None:
        vol = rp.create_volume()
        print(f"volume oluşturuldu: {vol}")
    else:
        print(f"volume mevcut: {vol}")
    state = read_state()
    state["volume"] = {
        "id": vol["id"],
        "name": vol["name"],
        "dataCenter": vol["dataCenter"],
        "size": vol["size"],
    }
    write_state(state)
    return 0


def cmd_up(rp: Runpod, args: argparse.Namespace) -> int:
    runtime = load_runtime()["llm"]
    engine_key = args.engine or os.environ.get("LLM_ENGINE") or runtime["engine"]
    model_key = args.model or os.environ.get("LLM_MODEL") or runtime["model"]
    state = read_state()
    if state.get("pod"):
        raise SystemExit(f"kayıtlı pod var: {state['pod']['id']}; önce `make down`")
    min_balance = load_infra()["runpod"].get("min_balance_usd", 5.0)
    balance = rp.balance()
    print(f"bakiye: {balance:.2f} USD (alt sınır {min_balance})")
    if balance < min_balance:
        raise SystemExit("bakiye alt sınırın altında; pod açılmadı")
    vol = rp.find_volume()
    if vol is None:
        raise SystemExit("network volume yok; önce `make volume`")
    overrides = parse_overrides(args.override)
    max_hours = args.max_hours or load_infra()["watchdog"]["max_hours"]
    deadline = watchdog_deadline(max_hours)
    body = pod_body(engine_key, model_key, vol["id"], args.download, overrides, deadline)
    until = time.strftime("%H:%M UTC", time.gmtime(deadline))
    idle_min = load_infra()["watchdog"]["idle_minutes"]
    print(
        f"bekçi: GPU {idle_min} dk boşta kalırsa ya da {max_hours} saat dolunca "
        f"({until}) pod kendini siler"
    )
    print(
        f"pod oluşturuluyor: {body['name']} {body['gpu']['id']} {body['dataCenterIds']} "
        f"{rp.cfg['gpu_hourly_usd']} USD/saat"
    )
    pod = rp.create_pod(
        body, retries=rp.cfg.get("create_retries", 0), wait_s=rp.cfg.get("create_retry_s", 30)
    )
    engine = load_engines()[engine_key]
    state["pod"] = {
        "id": pod["id"],
        "name": pod.get("name"),
        "engine": engine_key,
        "model": model_key,
        "created_at": now(),
        "created_monotonic_hint": time.time(),
        "cost_per_hr": pod.get("cost", rp.cfg["gpu_hourly_usd"]),
        "llm_port": engine.port,
        "embedding_port": load_embedding_server()["port"],
        "download": args.download,
        "overrides": overrides,
        "started_monotonic": time.time(),
        "watchdog_deadline": deadline,
    }
    write_state(state)
    print(f"pod: {pod['id']} durum={pod.get('status')} ücret={pod.get('cost')} USD/saat")
    cuda = rp.get_pod(pod["id"]).json().get("cudaVersion")
    if cuda and _version(cuda) < _version(rp.cfg["min_cuda_version"]):
        print(f"host CUDA {cuda} < {rp.cfg['min_cuda_version']}; pod siliniyor")
        return cmd_down(rp, args)
    print(f"host CUDA: {cuda}")
    print(f"LLM: {proxy_url(pod['id'], engine.port)}/v1")
    return 0


def cmd_wait(rp: Runpod, args: argparse.Namespace) -> int:
    pod = read_state().get("pod") or {}
    if not pod:
        raise SystemExit("kayıtlı pod yok")
    key = ensure_env_secret("LLM_API_KEY")
    url = proxy_url(pod["id"], pod["llm_port"]) + "/v1/models"
    started = pod.get("started_monotonic", pod["created_monotonic_hint"])
    deadline = time.time() + args.timeout
    with httpx.Client(timeout=15, headers={"Authorization": f"Bearer {key}"}) as http:
        if pod.get("awaiting_restart"):
            # After a reconfigure the old server may still answer for a moment; wait until it
            # goes down so that "ready" means the new configuration.
            down_deadline = time.time() + 180
            while time.time() < down_deadline:
                try:
                    if http.get(url).status_code != 200:
                        break
                except httpx.HTTPError:
                    break
                time.sleep(3)
            else:
                print("uyarı: eski sunucu 180 sn içinde kapanmadı")
            state = read_state()
            state["pod"].pop("awaiting_restart", None)
            write_state(state)
        while time.time() < deadline:
            try:
                r = http.get(url)
                if r.status_code == 200:
                    took = time.time() - started
                    served = r.json()["data"][0]["id"]
                    print(f"hazır: başlatmadan {took:.0f} sn sonra; {served}")
                    state = read_state()
                    state["pod"]["ready_after_s"] = round(took)
                    write_state(state)
                    return 0
            except httpx.HTTPError:
                pass
            time.sleep(10)
    print("zaman aşımı: servis hazır olmadı")
    return 1


def cmd_reconfigure(rp: Runpod, args: argparse.Namespace) -> int:
    """Change model, engine or server settings of the running pod without deleting it: the
    entrypoint (and image, ports) are patched, the container restarts on the same machine,
    so the image is not pulled again."""
    state = read_state()
    pod = state.get("pod")
    if not pod:
        raise SystemExit("kayıtlı pod yok; önce `make up`")
    engine_key = args.engine or pod["engine"]
    model_key = args.model or pod["model"]
    overrides = parse_overrides(args.override)
    vol = rp.find_volume()
    deadline = pod.get("watchdog_deadline") or watchdog_deadline(
        load_infra()["watchdog"]["max_hours"]
    )
    body = pod_body(engine_key, model_key, vol["id"], args.download, overrides, deadline)
    patch = {k: body[k] for k in ("image", "ports", "env", "entrypoint")}
    r = rp.http.patch(f"/pods/{pod['id']}", json=patch)
    if r.status_code >= 400:
        raise SystemExit(f"PATCH başarısız: HTTP {r.status_code} {r.text[:800]}")
    engine = load_engines()[engine_key]
    pod |= {
        "engine": engine_key,
        "model": model_key,
        "overrides": overrides,
        "llm_port": engine.port,
        "started_monotonic": time.time(),
        "reconfigured_at": now(),
        "awaiting_restart": True,
        "watchdog_deadline": deadline,
    }
    pod.setdefault("reconfigurations", []).append(
        {"at": now(), "engine": engine_key, "model": model_key, "overrides": overrides}
    )
    state["pod"] = pod
    write_state(state)
    print(f"yeniden yapılandırıldı: {pod['id']} → {engine_key}/{model_key} {overrides}")
    return 0


def cmd_extend(rp: Runpod, args: argparse.Namespace) -> int:
    """Move the self-delete deadline of the running pod (no restart: writes the pod's
    /tmp/watchdog_deadline through the exec API; the next reconfigure carries it in env)."""
    state = read_state()
    pod = state.get("pod")
    if not pod:
        raise SystemExit("kayıtlı pod yok")
    deadline = int(max(pod.get("watchdog_deadline") or 0, time.time()) + float(args.hours) * 3600)
    if deadline - time.time() > 24 * 3600:
        raise SystemExit("son tarih şu andan en fazla 24 saat sonra olabilir")
    cmd = ["sh", "-c", f"echo {deadline} > /tmp/watchdog_deadline && cat /tmp/watchdog_deadline"]
    r = rp.http.post(f"/pods/{pod['id']}/exec", json={"command": cmd, "timeoutSeconds": 20})
    if r.status_code >= 400 or str(deadline) not in r.text:
        raise SystemExit(f"uzatma başarısız: HTTP {r.status_code} {r.text[:300]}")
    pod["watchdog_deadline"] = deadline
    write_state(state)
    print(f"yeni son tarih: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(deadline))}")
    return 0


def cmd_status(rp: Runpod, _: argparse.Namespace) -> int:
    state = read_state()
    print(yaml.safe_dump(state, allow_unicode=True, sort_keys=False))
    if pod := state.get("pod"):
        r = rp.get_pod(pod["id"])
        print(
            f"get-pod: HTTP {r.status_code}",
            r.json().get("status") if r.status_code == 200 else "",
        )
    return 0


def cmd_down(rp: Runpod, _: argparse.Namespace) -> int:
    state = read_state()
    pod = state.get("pod")
    if not pod:
        print("kayıtlı pod yok")
    else:
        rp.delete_pod(pod["id"])
        for _ in range(30):
            if rp.get_pod(pod["id"]).status_code == 404:
                break
            time.sleep(2)
        code = rp.get_pod(pod["id"]).status_code
        hours = (time.time() - pod["created_monotonic_hint"]) / 3600
        cost = hours * float(pod["cost_per_hr"])
        print(
            f"silindi: {pod['id']} get-pod HTTP {code}; süre {hours:.2f} saat, "
            f"yaklaşık {cost:.2f} USD"
        )
        if code != 404:
            raise SystemExit("pod hâlâ görünüyor; elle kontrol et")
        history = state.setdefault("history", [])
        history.append(
            {
                **pod,
                "deleted_at": now(),
                "hours": round(hours, 3),
                "approx_cost_usd": round(cost, 2),
            }
        )
        state.pop("pod")
        write_state(state)
    ours = [p for p in rp.list_pods() if p.get("name", "").startswith(rp.cfg["pod_name"])]
    print(f"list-pods: bu pakete ait pod sayısı {len(ours)}")
    return 0 if not ours else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("balance")
    sub.add_parser("volume")
    up = sub.add_parser("up")
    up.add_argument("--engine")
    up.add_argument("--model")
    up.add_argument("--download", action="store_true", help="ağırlıkları volume'a indir")
    up.add_argument("--override", action="append", help="sunucu ayarı, ör. max_num_seqs=64")
    up.add_argument("--max-hours", type=float, help="bekçinin en uzun ömrü (saat)")
    ex = sub.add_parser("extend")
    ex.add_argument("--hours", type=float, required=True)
    rc = sub.add_parser("reconfigure")
    rc.add_argument("--engine")
    rc.add_argument("--model")
    rc.add_argument("--download", action="store_true")
    rc.add_argument("--override", action="append")
    w = sub.add_parser("wait")
    w.add_argument("--timeout", type=float, default=1800)
    sub.add_parser("status")
    sub.add_parser("down")
    dl = sub.add_parser("download")
    dl.add_argument("--clean", action="append", default=[], help="önce silinecek repo önbelleği")
    sub.add_parser("download-down")
    args = ap.parse_args()
    rp = Runpod()
    return {
        "balance": cmd_balance,
        "volume": cmd_volume,
        "up": cmd_up,
        "wait": cmd_wait,
        "status": cmd_status,
        "down": cmd_down,
        "reconfigure": cmd_reconfigure,
        "extend": cmd_extend,
        "download": cmd_download,
        "download-down": cmd_download_down,
    }[args.cmd](rp, args)


if __name__ == "__main__":
    raise SystemExit(main())
