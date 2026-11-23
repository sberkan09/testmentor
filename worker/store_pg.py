"""Postgres implementation of `worker.store.ProjectStore` (psycopg 3; docs/tasarim.md, Veri
modeli; Sunucu mimarisi ve API).

- Schema `worker/schema.sql`, applied idempotently by `connect`.
- One connection in autocommit mode; `transaction()` opens a transaction and every method runs in
  its own nested one (a savepoint inside an outer transaction), so a command's writes commit
  together and a failed compare-and-set rolls back only itself.
- `put_node` / `remove_node` lock the current row (`FOR UPDATE`) and compare versions; a
  concurrent insert of a new node hits the primary key and is reported as `VersionConflict`.
- Event numbers are per project, assigned under a transaction-scoped advisory lock.
- Values are stored as JSON from the pydantic models (`model_dump(mode="json")`), so a reloaded
  node is equal to the stored one and hashes are unchanged.

Used from the orchestrator's event loop thread only (one connection, synchronous calls).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import psycopg
from psycopg import errors
from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from core.events import Event, EventRecord
from core.nodes import Node, NodeKind, NodeRef, Result, Status
from core.store import VersionConflict
from worker.store import JobRecord, ProjectRecord

SCHEMA = Path(__file__).with_name("schema.sql")
_EVENT = TypeAdapter(Event)
TABLES = (
    "tm_projects",
    "tm_nodes",
    "tm_node_versions",
    "tm_output_cache",
    "tm_events",
    "tm_jobs",
)


def _json(model: Any) -> Jsonb:
    return Jsonb(model.model_dump(mode="json"))


class PostgresStore:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    @classmethod
    def connect(cls, dsn: str) -> PostgresStore:
        conn = psycopg.connect(dsn, autocommit=True)
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    def truncate(self) -> None:
        """Empty every table (tests)."""
        self._conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY")

    def transaction(self) -> AbstractContextManager[object]:
        return self._conn.transaction()

    # OutputCache --------------------------------------------------------------------------------

    def get(self, project_id: str, cache_key: str) -> Result | None:
        row = self._conn.execute(
            "SELECT result FROM tm_output_cache WHERE project_id = %s AND cache_key = %s",
            (project_id, cache_key),
        ).fetchone()
        return Result.model_validate(row[0]) if row else None

    def put(self, project_id: str, cache_key: str, result: Result) -> None:
        self._conn.execute(
            "INSERT INTO tm_output_cache (project_id, cache_key, result) VALUES (%s, %s, %s) "
            "ON CONFLICT (project_id, cache_key) DO UPDATE SET result = EXCLUDED.result",
            (project_id, cache_key, _json(result)),
        )

    # Nodes --------------------------------------------------------------------------------------

    def get_node(self, project_id: str, ref: NodeRef) -> Node | None:
        row = self._conn.execute(
            "SELECT node FROM tm_nodes WHERE project_id = %s AND kind = %s AND key = %s",
            (project_id, ref.kind.value, ref.key),
        ).fetchone()
        return Node.model_validate(row[0]) if row else None

    def _locked_version(self, project_id: str, ref: NodeRef) -> int:
        row = self._conn.execute(
            "SELECT version FROM tm_nodes WHERE project_id = %s AND kind = %s AND key = %s "
            "FOR UPDATE",
            (project_id, ref.kind.value, ref.key),
        ).fetchone()
        return row[0] if row else 0

    def put_node(self, project_id: str, node: Node, *, expected_version: int) -> None:
        ref = node.ref
        try:
            with self._conn.transaction():
                current = self._locked_version(project_id, ref)
                if current != expected_version or node.version != expected_version + 1:
                    raise VersionConflict(ref, expected_version, self.get_node(project_id, ref))
                params = (node.version, node.status.value, _json(node))
                if current:
                    self._conn.execute(
                        "UPDATE tm_nodes SET version = %s, status = %s, node = %s "
                        "WHERE project_id = %s AND kind = %s AND key = %s",
                        (*params, project_id, ref.kind.value, ref.key),
                    )
                else:
                    self._conn.execute(
                        "INSERT INTO tm_nodes (project_id, kind, key, version, status, node) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (project_id, ref.kind.value, ref.key, *params),
                    )
                self._conn.execute(
                    "INSERT INTO tm_node_versions (project_id, kind, key, version, node) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (project_id, ref.kind.value, ref.key, node.version, _json(node)),
                )
        except errors.UniqueViolation as exc:  # a concurrent writer created the node first
            raise VersionConflict(ref, expected_version, self.get_node(project_id, ref)) from exc

    def remove_node(self, project_id: str, ref: NodeRef, *, expected_version: int) -> None:
        with self._conn.transaction():
            current = self._locked_version(project_id, ref)
            if current == 0 or current != expected_version:
                raise VersionConflict(ref, expected_version, self.get_node(project_id, ref))
            self._conn.execute(
                "DELETE FROM tm_nodes WHERE project_id = %s AND kind = %s AND key = %s",
                (project_id, ref.kind.value, ref.key),
            )

    def set_status(self, project_id: str, ref: NodeRef, status: Status) -> None:
        cur = self._conn.execute(
            "UPDATE tm_nodes SET status = %s, "
            "node = jsonb_set(node, '{status}', to_jsonb(%s::text)) "
            "WHERE project_id = %s AND kind = %s AND key = %s",
            (status.value, status.value, project_id, ref.kind.value, ref.key),
        )
        if cur.rowcount != 1:
            raise KeyError(f"{project_id}: no node {ref}")

    def history(self, project_id: str, ref: NodeRef) -> list[Node]:
        rows = self._conn.execute(
            "SELECT node FROM tm_node_versions WHERE project_id = %s AND kind = %s AND key = %s "
            "ORDER BY id",
            (project_id, ref.kind.value, ref.key),
        ).fetchall()
        return [Node.model_validate(r[0]) for r in rows]

    def load(self, project_id: str) -> dict[NodeRef, Node]:
        rows = self._conn.execute(
            "SELECT kind, key, node FROM tm_nodes WHERE project_id = %s", (project_id,)
        ).fetchall()
        return {
            NodeRef(kind=NodeKind(kind), key=key): Node.model_validate(node)
            for kind, key, node in rows
        }

    # Event log ----------------------------------------------------------------------------------

    def append_event(self, project_id: str, event: Event, *, actor: str) -> int:
        with self._conn.transaction():
            self._conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (project_id,))
            (seq,) = self._conn.execute(
                "SELECT coalesce(max(seq), 0) + 1 FROM tm_events WHERE project_id = %s",
                (project_id,),
            ).fetchone()  # type: ignore[misc]
            self._conn.execute(
                "INSERT INTO tm_events (project_id, seq, actor, event) VALUES (%s, %s, %s, %s)",
                (project_id, seq, actor, Jsonb(_EVENT.dump_python(event, mode="json"))),
            )
        return int(seq)

    def events(self, project_id: str, *, after: int = 0) -> list[EventRecord]:
        rows = self._conn.execute(
            "SELECT seq, actor, event FROM tm_events WHERE project_id = %s AND seq > %s "
            "ORDER BY seq",
            (project_id, after),
        ).fetchall()
        return [
            EventRecord(seq=seq, actor=actor, event=_EVENT.validate_python(event))
            for seq, actor, event in rows
        ]

    # Projects and jobs --------------------------------------------------------------------------

    def save_project(self, record: ProjectRecord) -> None:
        self._conn.execute(
            "INSERT INTO tm_projects (project_id, record) VALUES (%s, %s) "
            "ON CONFLICT (project_id) DO UPDATE SET record = EXCLUDED.record, updated_at = now()",
            (record.project_id, _json(record)),
        )

    def get_project(self, project_id: str) -> ProjectRecord | None:
        row = self._conn.execute(
            "SELECT record FROM tm_projects WHERE project_id = %s", (project_id,)
        ).fetchone()
        return ProjectRecord.model_validate(row[0]) if row else None

    def list_projects(self) -> list[ProjectRecord]:
        rows = self._conn.execute("SELECT record FROM tm_projects ORDER BY project_id").fetchall()
        return [ProjectRecord.model_validate(r[0]) for r in rows]

    def put_job(self, project_id: str, job: JobRecord) -> None:
        self._conn.execute(
            "INSERT INTO tm_jobs (project_id, job_id, record) VALUES (%s, %s, %s) "
            "ON CONFLICT (project_id, job_id) DO UPDATE SET record = EXCLUDED.record, "
            "updated_at = now()",
            (project_id, job.job_id, _json(job)),
        )

    def jobs(self, project_id: str) -> list[JobRecord]:
        rows = self._conn.execute(
            "SELECT record FROM tm_jobs WHERE project_id = %s ORDER BY job_id", (project_id,)
        ).fetchall()
        return [JobRecord.model_validate(r[0]) for r in rows]
