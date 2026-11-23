"""A throwaway Postgres for the store tests (paket 5).

`TESTMENTOR_PG_DSN` set: that database is used (its `tm_*` tables are truncated per test).
Otherwise a temporary cluster is created with the local server binaries
(`/usr/lib/postgresql/*/bin/initdb`, or `initdb` on PATH), listening on a Unix socket only, and
removed afterwards. As root the binaries run as the `postgres` user (initdb refuses root). With
neither, the tests are skipped.
"""

from __future__ import annotations

import glob
import os
import pwd
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager


def _bindir() -> str | None:
    found = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"))
    if found:
        return os.path.dirname(found[-1])
    initdb = shutil.which("initdb")
    return os.path.dirname(initdb) if initdb else None


@contextmanager
def temporary_cluster() -> Iterator[str | None]:
    """Yields a DSN, or None when no server can be started (reason printed)."""
    if dsn := os.environ.get("TESTMENTOR_PG_DSN"):
        yield dsn
        return
    bindir = _bindir()
    if bindir is None:
        yield None
        return
    prefix: list[str] = []
    owner = None
    if os.geteuid() == 0:
        try:
            owner = pwd.getpwnam("postgres")
        except KeyError:
            yield None
            return
        prefix = ["runuser", "-u", "postgres", "--"]
    root = tempfile.mkdtemp(prefix="tmpg", dir="/tmp")  # short: socket paths are limited
    if owner is not None:
        os.chown(root, owner.pw_uid, owner.pw_gid)
    data = os.path.join(root, "data")

    def run(*args: str) -> None:
        subprocess.run([*prefix, *args], check=True, capture_output=True, timeout=120)

    try:
        run(f"{bindir}/initdb", "-D", data, "-U", "postgres", "--auth=trust", "-E", "UTF8")
        run(
            f"{bindir}/pg_ctl",
            "-D",
            data,
            "-o",
            f"-p 5432 -k {root} -c listen_addresses='' -c fsync=off",
            "-w",
            "-l",
            os.path.join(root, "log"),
            "start",
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"temporary Postgres could not start: {exc}")
        shutil.rmtree(root, ignore_errors=True)
        yield None
        return
    try:
        yield f"host={root} port=5432 user=postgres dbname=postgres"
    finally:
        try:
            run(f"{bindir}/pg_ctl", "-D", data, "-m", "immediate", "stop")
        finally:
            shutil.rmtree(root, ignore_errors=True)
