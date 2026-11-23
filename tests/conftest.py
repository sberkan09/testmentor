"""Shared fixtures. `pg_dsn` / `pg_store`: Postgres for the store tests (tests/pg.py); skipped
when no server is available. `make pg-test` runs only those."""

from __future__ import annotations

import pytest

from tests.pg import temporary_cluster


@pytest.fixture(scope="session")
def pg_dsn():
    with temporary_cluster() as dsn:
        if dsn is None:
            pytest.skip("no Postgres: set TESTMENTOR_PG_DSN or install the server binaries")
        yield dsn


@pytest.fixture
def pg_store(pg_dsn):
    from worker.store_pg import PostgresStore

    store = PostgresStore.connect(pg_dsn)
    store.truncate()
    yield store
    store.close()
