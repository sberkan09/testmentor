#!/usr/bin/env bash
# Kurulum doğrulaması (paket 12). Denetimler uygulama kapsayıcısının içinde koşar (Python orada).
#   bash verify.sh app  [PROJE]   uygulama: sağlık, giriş kipi, küçük bir projenin üretimi (sahte model)
#   bash verify.sh full [PROJE]   + model sunucusu ve embedding: model listesi, bir sohbet, bir vektör
#   bash verify.sh egress [PROJE] kapsayıcıdan dışarıya erişim yok mu (internetsiz ağ denetimi)
set -euo pipefail
cd "$(dirname "$0")"
MODE=${1:-full}
PROJECT=${2:-testmentor}
docker compose -p "$PROJECT" -f compose.yaml --env-file .env exec -T -e MODE="$MODE" app python - <<'PY'
import json, os, sys, time, urllib.request

mode = os.environ["MODE"]
base = "http://localhost:8000"
fails = []

def get(url, headers=None, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")

def check(name, fn):
    try:
        detail = fn()
        print(f"  [tamam] {name}" + (f": {detail}" if detail else ""), flush=True)
    except Exception as exc:
        print(f"  [HATA]  {name}: {exc}", flush=True)
        fails.append(name)

if mode == "egress":
    for url in ("https://huggingface.co", "https://pypi.org", "http://example.com"):
        try:
            urllib.request.urlopen(url, timeout=8)
            print(f"  [UYARI] dışarıya erişim VAR: {url}")
            fails.append(url)
        except Exception as exc:
            print(f"  [tamam] dışarıya erişim yok: {url} ({type(exc).__name__})")
    sys.exit(1 if fails else 0)

check("uygulama ayakta", lambda: f"giriş kipi {get(base + '/auth/config')['mode']}")

if mode == "app":
    def small_project():
        boundary = "x7c1"
        meta = {"name": "Doğrulama", "key": "DOGRULAMA", "mapping": {"text": "text", "id": "id"}}
        csv = "id,text\nR1,Kullanıcı parola ile giriş yapabilmelidir.\nR2,Sistem raporu PDF olarak dışa aktarmalıdır.\n"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"meta\"\r\n\r\n{json.dumps(meta)}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.csv\"\r\n"
            f"Content-Type: text/csv\r\n\r\n{csv}\r\n--{boundary}--\r\n"
        ).encode()
        get(base + "/projects", {"Content-Type": f"multipart/form-data; boundary={boundary}",
                                 "X-User": "dogrulama"}, body)
        for _ in range(120):
            s = get(base + "/projects/DOGRULAMA/snapshot")
            if not s["jobs"] and all(n["status"] == "fresh" for n in s["nodes"]):
                cases = sum(1 for n in s["nodes"] if n["ref"]["kind"] == "test_case")
                if not cases:
                    raise RuntimeError("test durumu üretilmedi")
                return f"{cases} test durumu"
            time.sleep(1)
        raise RuntimeError("üretim bitmedi")
    check("küçük proje uçtan uca (sahte model, Postgres)", small_project)
else:
    key = os.environ.get("LLM_API_KEY", "")
    auth = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    sys.path.insert(0, "/app")  # the app's own settings: same addresses the server uses
    from services.settings import load_embedding_settings, load_llm_settings
    llm = load_llm_settings("/app/config").base_url.rstrip("/")
    emb = load_embedding_settings("/app/config").base_url.rstrip("/")
    model = {}
    def models():
        ids = [m["id"] for m in get(llm + "/models", auth)["data"]]
        model["id"] = ids[0]
        return ", ".join(ids)
    check(f"model sunucusu {llm}", models)
    def chat():
        body = json.dumps({"model": model["id"], "max_tokens": 16, "temperature": 0,
                           "messages": [{"role": "user", "content": "Sadece 'tamam' yaz."}],
                           "chat_template_kwargs": {"enable_thinking": False}}).encode()
        r = get(llm + "/chat/completions", auth, body, timeout=300)
        return repr(r["choices"][0]["message"]["content"][:40])
    check("bir sohbet isteği", chat)
    def embed():
        name = get(emb + "/models", auth)["data"][0]["id"]
        body = json.dumps({"model": name, "input": ["parola ile giriş"]}).encode()
        v = get(emb + "/embeddings", auth, body)["data"][0]["embedding"]
        return f"{name}, {len(v)} boyut"
    check(f"embedding {emb}", embed)

if fails:
    print(f"Doğrulama BAŞARISIZ: {', '.join(fails)}")
    sys.exit(1)
print("Doğrulama: tamam.")
PY
