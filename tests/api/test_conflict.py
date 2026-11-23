"""Paket 6 done test 2: two users editing the same test case; the stale one is rejected (409,
current versions), a locked node refuses the other user (423)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

PID = "DEN"


def first_case(project: dict[str, Any]) -> dict[str, Any]:
    return next(n for n in project["nodes"] if n["ref"]["kind"] == "test_case")


def edit(case: dict[str, Any], title: str, version: int | None) -> dict[str, Any]:
    key = case["ref"]["key"]
    body: dict[str, Any] = {
        "command": {
            "type": "edit_test_case",
            "case": key,
            "content": dict(case["content"], title=title),
        }
    }
    if version is not None:
        body["expected_versions"] = {f"test_case:{key}": version}
    return body


def send(client: TestClient, user: str, body: dict[str, Any]) -> Any:
    return client.post(f"/projects/{PID}/commands", json=body, headers={"X-User": user})


def test_same_version_second_edit_is_409_with_current_version(
    client: TestClient, project: dict[str, Any]
) -> None:
    case = first_case(project)
    v = case["version"]
    ok = send(client, "ayse", edit(case, "Ayşe'nin", v))
    assert ok.status_code == 200 and ok.json()["accepted"] is True

    late = send(client, "bora", edit(case, "Bora'nın", v))
    assert late.status_code == 409
    body = late.json()
    assert body["accepted"] is False and body["reason"].startswith("version_conflict")
    assert body["current_versions"] == {f"test_case:{case['ref']['key']}": v + 1}

    fresh = next(
        n
        for n in client.get(f"/projects/{PID}/snapshot").json()["nodes"]
        if n["ref"] == case["ref"]
    )
    assert fresh["content"]["title"] == "Ayşe'nin"


def test_locked_node_refuses_other_user(client: TestClient, project: dict[str, Any]) -> None:
    case = first_case(project)
    ref = case["ref"]
    assert (
        client.post(
            f"/projects/{PID}/locks", json={"ref": ref}, headers={"X-User": "ayse"}
        ).status_code
        == 200
    )
    # Refreshing is fine; another user is refused.
    assert (
        client.post(
            f"/projects/{PID}/locks", json={"ref": ref}, headers={"X-User": "ayse"}
        ).status_code
        == 200
    )
    other = client.post(f"/projects/{PID}/locks", json={"ref": ref}, headers={"X-User": "bora"})
    assert other.status_code == 423 and other.json()["locked"] is False

    refused = send(client, "bora", edit(case, "Bora'nın", None))
    assert refused.status_code == 423
    assert refused.json()["accepted"] is False and refused.json()["reason"].startswith("locked")

    assert send(client, "ayse", edit(case, "Ayşe'nin", None)).status_code == 200
    snap = client.get(f"/projects/{PID}/snapshot").json()
    assert snap["locks"] == {f"test_case:{ref['key']}": "ayse"}


def test_invalid_and_missing_actor(client: TestClient, project: dict[str, Any]) -> None:
    case = first_case(project)
    assert client.post(f"/projects/{PID}/commands", json=edit(case, "x", None)).status_code == 400

    bad = send(client, "ayse", {"command": {"type": "nope"}})
    assert bad.status_code == 422
    assert bad.json()["accepted"] is False and bad.json()["reason"].startswith("invalid")

    unknown = send(
        client, "ayse", {"command": {"type": "pin", "node": {"kind": "test_case", "key": "YOK:1"}}}
    )
    assert unknown.status_code == 422 and unknown.json()["reason"].startswith("invalid")

    undo = send(client, "ayse", {"command": {"type": "undo"}})
    assert undo.status_code == 409 and undo.json()["reason"] == "nothing_to_undo"
