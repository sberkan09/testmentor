"""Paket 6 done test 1: the client survives a dropped connection with the same state as the server.

A client builds its node map from the snapshot and the events; the connection drops while
another user commands; the client reconnects with its last `seq` and the node map equals a fresh
snapshot. When the missed events fell out of the ring, a `snapshot` message arrives instead.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.api.fake_service import FakeProjectService

PID = "DEN"


def nodes_of(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f"{n['ref']['kind']}:{n['ref']['key']}": n for n in snapshot["nodes"]}


def apply(nodes: dict[str, dict[str, Any]], event: dict[str, Any]) -> None:
    if event["type"] == "node_updated" or event["type"] == "node_created":
        n = event["payload"]["node"]
        nodes[f"{n['ref']['kind']}:{n['ref']['key']}"] = n


def case_keys(snapshot: dict[str, Any]) -> list[str]:
    return [k for k in nodes_of(snapshot) if k.startswith("test_case:")]


def edit_body(snapshot: dict[str, Any], key: str, title: str) -> dict[str, Any]:
    content = dict(nodes_of(snapshot)[key]["content"], title=title)
    return {
        "command": {
            "type": "edit_test_case",
            "case": key.removeprefix("test_case:"),
            "content": content,
        }
    }


def post(client: TestClient, user: str, body: dict[str, Any]) -> dict[str, Any]:
    r = client.post(f"/projects/{PID}/commands", json=body, headers={"X-User": user})
    assert r.status_code == 200, r.text
    return r.json()


def test_reconnect_receives_missed_events_and_state_matches(
    client: TestClient, project: dict[str, Any]
) -> None:
    keys = case_keys(project)
    assert len(keys) >= 2
    nodes = nodes_of(project)
    last = project["seq"]

    with client.websocket_connect(f"/projects/{PID}/events?after={last}&user=bora") as ws:
        ws.send_text('{"type":"ping"}')
        assert ws.receive_json() == {"type": "pong"}
        post(client, "ayse", edit_body(project, keys[0], "Birinci düzenleme"))
        for _ in range(2):  # node_updated, command_applied
            ev = ws.receive_json()
            assert ev["seq"] == last + 1
            last = ev["seq"]
            apply(nodes, ev)
    # Connection is down; others keep working.
    post(client, "ayse", edit_body(project, keys[1], "Kopukken düzenleme"))
    post(
        client,
        "ayse",
        {
            "command": {
                "type": "pin",
                "node": {"kind": "test_case", "key": keys[0].removeprefix("test_case:")},
            }
        },
    )

    with client.websocket_connect(f"/projects/{PID}/events?after={last}&user=bora") as ws:
        for _ in range(4):
            ev = ws.receive_json()
            assert ev["seq"] == last + 1, "events arrive in order, without gaps or repeats"
            last = ev["seq"]
            apply(nodes, ev)

    fresh = client.get(f"/projects/{PID}/snapshot").json()
    assert last == fresh["seq"]
    assert nodes == nodes_of(fresh)
    assert nodes[keys[0]]["pinned"] is True
    assert nodes[keys[1]]["content"]["title"] == "Kopukken düzenleme"


def test_live_events_after_replay_are_not_repeated(
    client: TestClient, service: FakeProjectService, project: dict[str, Any]
) -> None:
    keys = case_keys(project)
    base = project["seq"]
    post(client, "ayse", edit_body(project, keys[0], "Önce"))
    with client.websocket_connect(f"/projects/{PID}/events?after={base}&user=bora") as ws:
        assert [ws.receive_json()["seq"] for _ in range(2)] == [base + 1, base + 2]
        post(client, "ayse", edit_body(project, keys[1], "Sonra"))
        assert [ws.receive_json()["seq"] for _ in range(2)] == [base + 3, base + 4]
        service.publish_progress(PID, "tok")
        progress = ws.receive_json()
        assert progress["type"] == "job_progress" and progress["payload"] == {"text": "tok"}
        assert progress["seq"] == base + 4, "job_progress does not advance seq"


def test_ring_overflow_sends_snapshot_message(
    client: TestClient, service: FakeProjectService, project: dict[str, Any]
) -> None:
    service.ring_size = 2
    keys = case_keys(project)
    old = project["seq"]
    for i in range(3):
        post(client, "ayse", edit_body(project, keys[0], f"Düzenleme {i}"))

    with client.websocket_connect(f"/projects/{PID}/events?after={old}&user=bora") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        fresh = client.get(f"/projects/{PID}/snapshot").json()
        assert msg["snapshot"] == fresh
        assert msg["snapshot"]["seq"] == old + 6

    # Without `after` the first message is a snapshot as well.
    with client.websocket_connect(f"/projects/{PID}/events?user=bora") as ws:
        assert ws.receive_json()["type"] == "snapshot"


def test_unknown_project_is_refused(client: TestClient) -> None:
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/projects/YOK/events"):
        pass
