"""`python -m api.users add NAME | remove NAME | list`: the users of password login (paket 10).

The file is `auth.users_file` of config/runtime.yaml (or `TESTMENTOR_USERS_FILE`); it holds
scrypt hashes only and stays out of git. `add` asks for the password twice on a terminal, or
reads one line from stdin when it is not a terminal (scripts, `docker compose exec -T`).
Adding an existing user changes the password.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from api.auth import UsersFile, load_auth_settings


def _read_password(min_chars: int) -> str:
    if sys.stdin.isatty():
        first = getpass.getpass("Parola: ")
        if getpass.getpass("Parola (tekrar): ") != first:
            raise SystemExit("parolalar aynı değil")
    else:
        first = sys.stdin.readline().rstrip("\r\n")
    if len(first) < min_chars:
        raise SystemExit(f"parola en az {min_chars} karakter olmalı")
    return first


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m api.users", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("add", help="kullanıcı ekle ya da parolasını değiştir").add_argument("name")
    sub.add_parser("remove", help="kullanıcıyı sil").add_argument("name")
    sub.add_parser("list", help="kullanıcıları listele")
    args = ap.parse_args(argv)
    settings = load_auth_settings()
    users = UsersFile(settings.users_file)
    if args.cmd == "add":
        try:
            users.set_password(args.name, _read_password(settings.min_password_chars))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"{args.name} kaydedildi ({users.path})")
    elif args.cmd == "remove":
        if not users.remove(args.name):
            raise SystemExit(f"{args.name} yok")
        print(f"{args.name} silindi")
    else:
        for name in sorted(users.load()):
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
