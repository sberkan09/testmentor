"""Password login (paket 10): scrypt hashes in the users file, signed expiring tokens, the
`password` mode of the API (REST, xlsx link, WebSocket) and the users command line tool. The
default `header` mode is what every other API test runs in."""

from __future__ import annotations

import io
import json

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.app import create_app
from api.auth import (
    Authenticator,
    AuthSettings,
    UsersFile,
    hash_password,
    load_auth_settings,
    verify_password,
)
from tests.api.conftest import META, csv_bytes
from tests.api.fake_service import FakeProjectService

SECRET = "s" * 40


def test_scrypt_hash_round_trip_and_format():
    h = hash_password("gizli-parola")
    assert h.startswith("scrypt$16384$8$1$")
    assert verify_password("gizli-parola", h)
    assert not verify_password("yanlış", h)
    assert hash_password("gizli-parola") != h  # salted
    assert not verify_password("x", "md5$abc") and not verify_password("x", "bozuk")


def test_users_file(tmp_path):
    users = UsersFile(tmp_path / "data" / "users.yaml")
    assert users.load() == {}
    users.set_password("ayşe", "parola123")
    users.set_password("mehmet", "parola456")
    raw = yaml.safe_load(users.path.read_text(encoding="utf-8"))
    assert list(raw["users"]) == ["ayşe", "mehmet"]
    assert "parola123" not in users.path.read_text(encoding="utf-8")
    assert oct(users.path.stat().st_mode & 0o777) == "0o600"
    with pytest.raises(ValueError):
        users.set_password("a b", "parola123")
    assert users.remove("mehmet") and not users.remove("mehmet")
    assert list(users.load()) == ["ayşe"]


def make_auth(tmp_path, clock=None, **kw) -> Authenticator:
    settings = AuthSettings(mode="password", users_file=str(tmp_path / "users.yaml"), **kw)
    UsersFile(settings.users_file).set_password("ayşe", "parola123")
    return Authenticator(settings, SECRET, **({"clock": clock} if clock else {}))


async def test_tokens_are_signed_and_expire(tmp_path):
    now = [1000.0]
    auth = make_auth(tmp_path, clock=lambda: now[0], token_hours=1)
    assert await auth.login("ayşe", "yanlış") is None
    assert await auth.login("yok", "parola123") is None
    token, expires = await auth.login("ayşe", "parola123")
    assert expires == 1000 + 3600 and auth.verify(token) == "ayşe"
    body, sig = token.split(".")
    assert auth.verify(f"{body}.{sig[:-2]}xx") is None
    assert (
        auth.verify(token + "x") is None and auth.verify("") is None and auth.verify(None) is None
    )
    other = Authenticator(auth.settings, "t" * 40, clock=lambda: now[0])
    assert other.verify(token) is None  # another secret
    now[0] = 1000 + 3601
    assert auth.verify(token) is None


def test_password_mode_needs_a_long_secret(tmp_path):
    settings = AuthSettings(mode="password", users_file=str(tmp_path / "u.yaml"))
    with pytest.raises(RuntimeError, match="TESTMENTOR_AUTH_SECRET"):
        Authenticator(settings, "kısa")
    assert Authenticator(AuthSettings(), "").mode == "header"


def test_settings_from_config_and_environment(monkeypatch):
    monkeypatch.delenv("TESTMENTOR_AUTH_MODE", raising=False)
    assert load_auth_settings().mode == "header"
    monkeypatch.setenv("TESTMENTOR_AUTH_MODE", "password")
    monkeypatch.setenv("TESTMENTOR_USERS_FILE", "/tmp/u.yaml")
    s = load_auth_settings()
    assert s.mode == "password" and s.users_file == "/tmp/u.yaml"


@pytest.fixture
def secured(tmp_path):
    service = FakeProjectService(ring_size=50)
    app = create_app(service, auth=make_auth(tmp_path), static_dir=tmp_path / "yok")
    with TestClient(app) as c:
        yield c, service


def login(client: TestClient, user="ayşe", password="parola123") -> str:
    r = client.post("/auth/login", json={"user": user, "password": password})
    assert r.status_code == 200, r.text
    assert r.json()["user"] == user
    return r.json()["token"]


def test_password_mode_rest(secured):
    client, service = secured
    assert client.get("/auth/config").json() == {"mode": "password"}
    assert client.post("/auth/login", json={"user": "ayşe", "password": "x"}).status_code == 401
    assert client.get("/projects").status_code == 401
    assert client.get("/projects", headers={"X-User": "ayse"}).status_code == 401
    assert client.get("/projects", headers={"Authorization": "Bearer bozuk"}).status_code == 401
    token = login(client)
    bearer = {"Authorization": f"Bearer {token}"}
    assert client.get("/projects", headers=bearer).status_code == 200
    r = client.post(
        "/projects",
        data={"meta": json.dumps(META)},
        files={"file": ("g.csv", csv_bytes(), "text/csv")},
        headers=bearer,
    )
    assert r.status_code == 200, r.text
    snap = client.get("/projects/DEN/snapshot", headers=bearer).json()
    cluster = next(n["ref"]["key"] for n in snap["nodes"] if n["ref"]["kind"] == "cluster")
    # the actor is the token's user; a forged X-User is ignored
    r = client.post(
        "/projects/DEN/commands",
        json={"command": {"type": "rename_cluster", "cluster": cluster, "name": "Raporlar"}},
        headers={**bearer, "X-User": "mehmet"},
    )
    assert r.status_code == 200, r.text
    assert service.events_after("DEN", 0)[-1].actor == "ayşe"
    r = client.post(
        "/projects/DEN/locks",
        json={"ref": {"kind": "requirement", "key": "R1"}},
        headers={**bearer, "X-User": "mehmet"},
    )
    assert r.status_code == 200 and service.snapshot("DEN").locks == {"requirement:R1": "ayşe"}
    # xlsx link: token in the query, only there
    assert client.get("/projects/DEN/matrix.xlsx").status_code == 401
    assert client.get(f"/projects/DEN/matrix.xlsx?token={token}").status_code == 200
    assert client.get(f"/projects/DEN/snapshot?token={token}").status_code == 401


def test_password_mode_websocket(secured):
    client, _ = secured
    token = login(client)
    client.post(
        "/projects",
        data={"meta": json.dumps(META)},
        files={"file": ("g.csv", csv_bytes(), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/projects/DEN/events") as ws:
            ws.receive_text()
    assert exc.value.code == 4401
    with client.websocket_connect(f"/projects/DEN/events?token={token}") as ws:
        assert json.loads(ws.receive_text())["type"] == "snapshot"


def test_header_mode_is_unchanged(client):
    assert client.get("/auth/config").json() == {"mode": "header"}
    assert client.post("/auth/login", json={"user": "a", "password": "b"}).status_code == 404
    assert client.get("/projects").status_code == 200


def test_users_command_line(tmp_path, monkeypatch, capsys):
    from api import users

    path = tmp_path / "u.yaml"
    monkeypatch.setenv("TESTMENTOR_USERS_FILE", str(path))
    monkeypatch.setattr("sys.stdin", io.StringIO("parola123\n"))
    assert users.main(["add", "ayşe"]) == 0
    assert verify_password("parola123", UsersFile(path).load()["ayşe"])
    monkeypatch.setattr("sys.stdin", io.StringIO("kısa\n"))
    with pytest.raises(SystemExit, match="en az 8"):
        users.main(["add", "mehmet"])
    assert users.main(["list"]) == 0
    assert capsys.readouterr().out.strip().endswith("ayşe")
    assert users.main(["remove", "ayşe"]) == 0
    with pytest.raises(SystemExit):
        users.main(["remove", "ayşe"])
