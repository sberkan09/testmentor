"""Login for the pilot (docs/tasarim.md, API → Kurallar; paket 10).

`auth.mode` (config/runtime.yaml, or `TESTMENTOR_AUTH_MODE`):
- `header` (default; development and tests): the actor is the `X-User` header.
- `password`: users log in with a name and password. Users live in `auth.users_file` (outside
  git), each with a scrypt hash (`hashlib.scrypt`); `python -m api.users add NAME` adds one. A
  login returns a token: the user name and expiry signed with HMAC-SHA256 under the secret in the
  environment variable `auth.secret_env` (`TESTMENTOR_AUTH_SECRET`, from `.env`). REST requests
  carry it as `Authorization: Bearer`, the WebSocket and the xlsx download link as `?token=`;
  the actor of a command is the token's user and `X-User` is ignored.

Per-project permissions are still a later version: every logged-in user sees every project.
The users file is read on every login, so a user added while the server runs can log in at once.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["header", "password"]

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
_NAME = re.compile(r"^[\w.@-]{1,64}$")


class AuthSettings(BaseModel):
    """`auth:` of config/runtime.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Mode = "header"
    users_file: str = "data/users.yaml"
    """Relative paths are resolved against the working directory (the repository root)."""
    token_hours: float = Field(default=12, gt=0)
    secret_env: str = "TESTMENTOR_AUTH_SECRET"
    min_secret_chars: int = Field(default=32, ge=16)
    min_password_chars: int = Field(default=8, ge=1)


def load_auth_settings(config_dir: str | Path = "config") -> AuthSettings:
    """Overrides: `TESTMENTOR_AUTH_MODE`, `TESTMENTOR_USERS_FILE` (Compose sets both)."""
    from services.settings import load_runtime

    raw = dict(load_runtime(config_dir).get("auth") or {})
    if mode := os.environ.get("TESTMENTOR_AUTH_MODE", "").strip().lower():
        raw["mode"] = mode
    if users := os.environ.get("TESTMENTOR_USERS_FILE", "").strip():
        raw["users_file"] = users
    return AuthSettings.model_validate(raw)


# Passwords ------------------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """`scrypt$<n>$<r>$<p>$<salt>$<hash>` (base64url)."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        n_, r_, p_ = int(n), int(r), int(p)
        expected = _unb64(digest)
        got = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt),
            n=n_,
            r=r_,
            p=p_,
            dklen=len(expected),
            maxmem=256 * n_ * r_ + 2**20,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


_DUMMY_HASH = hash_password("dummy-password", salt=b"\0" * 16)
"""Checked for an unknown user, so the answer takes as long as for a wrong password."""


# Users file -----------------------------------------------------------------------------------


class UsersFile:
    """`{users: {<name>: {hash: <scrypt hash>}}}` in YAML."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        users = raw.get("users") or {}
        return {str(name): str(entry["hash"]) for name, entry in users.items()}

    def _save(self, users: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"users": {name: {"hash": h} for name, h in sorted(users.items())}}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    def set_password(self, name: str, password: str) -> None:
        if not _NAME.match(name):
            raise ValueError("kullanıcı adı yalnızca harf, rakam, '.', '_', '-', '@' içerebilir")
        users = self.load()
        users[name] = hash_password(password)
        self._save(users)

    def remove(self, name: str) -> bool:
        users = self.load()
        if name not in users:
            return False
        del users[name]
        self._save(users)
        return True


# Tokens ---------------------------------------------------------------------------------------


class Authenticator:
    def __init__(
        self, settings: AuthSettings, secret: str = "", clock: Callable[[], float] = time.time
    ) -> None:
        self.settings = settings
        self.mode: Mode = settings.mode
        self._secret = secret.encode("utf-8")
        self._clock = clock
        self.users = UsersFile(settings.users_file)
        if self.mode == "password" and len(secret) < settings.min_secret_chars:
            raise RuntimeError(
                f"auth.mode is password but {settings.secret_env} is missing or shorter than "
                f"{settings.min_secret_chars} characters (set it in .env)"
            )

    @classmethod
    def from_config(cls, config_dir: str | Path = "config") -> Authenticator:
        settings = load_auth_settings(config_dir)
        return cls(settings, os.environ.get(settings.secret_env, ""))

    def _sign(self, payload: bytes) -> str:
        return _b64(hmac.new(self._secret, payload, hashlib.sha256).digest())

    def issue(self, user: str) -> tuple[str, float]:
        expires = int(self._clock() + self.settings.token_hours * 3600)
        payload = json.dumps({"u": user, "exp": expires}, ensure_ascii=False).encode("utf-8")
        return f"{_b64(payload)}.{self._sign(payload)}", float(expires)

    def verify(self, token: str | None) -> str | None:
        """The user of a valid, unexpired token, else None."""
        if not token or self.mode != "password":
            return None
        try:
            body, signature = token.split(".", 1)
            payload = _unb64(body)
        except ValueError:
            return None
        if not hmac.compare_digest(signature, self._sign(payload)):
            return None
        try:
            data = json.loads(payload)
            user, expires = str(data["u"]), float(data["exp"])
        except (ValueError, KeyError, TypeError):
            return None
        return user if expires > self._clock() else None

    def check_password(self, user: str, password: str) -> bool:
        stored = self.users.load().get(user)
        ok = verify_password(password, stored or _DUMMY_HASH)
        return ok and stored is not None

    async def login(self, user: str, password: str) -> tuple[str, float] | None:
        """Token and expiry, or None. scrypt runs in a worker thread: the event loop (and so
        the orchestrator) is not held up by a login."""
        if self.mode != "password":
            return None
        if not await asyncio.to_thread(self.check_password, user.strip(), password):
            return None
        return self.issue(user.strip())
