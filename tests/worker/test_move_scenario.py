"""Paket 5 done test (docs/tasarim.md, Geliştirme planı; bayatlama tablosu, first row after D8):
moving R2 from A to B ends with exactly one incremental test call (B) and two label calls (A,
B); A's set is pruned without a call; the other clusters cost nothing. Undo costs no model call
and every node is back to its content before the move."""

from __future__ import annotations

from core.nodes import NodeKind
from services.fake_llm import FakeComplete
from tests.worker.helpers import calls, hashes, produced, ref, service
from worker.contracts import CommandRequest, MoveRequirement, Undo


async def test_move_then_undo():
    complete = FakeComplete()
    svc = service(complete=complete)
    before = await produced(svc)
    before_hashes = hashes(before)
    n0 = len(complete.requests)

    result = await svc.command(
        "P",
        CommandRequest(command=MoveRequirement(requirement="R2", to_cluster="B")),
        actor="ayse",
    )
    assert result.accepted, result
    await svc.wait_idle()

    moved = calls(complete.requests[n0:])
    assert moved == {
        ("TestCaseDelta", "B/incremental"): 1,
        ("ClusterLabel", "A/label"): 1,
        ("ClusterLabel", "B/label"): 1,
    }
    state = svc.runtime("P").state
    assert state.members("A") == ("R1",)
    assert state.members("B") == ("R2", "R3", "R4")
    assert state.node(ref(NodeKind.TEST_SET, "A")).produced_by.mode == "incremental"
    a_cases = [state.node(r).content for r in state.test_cases("A")]
    assert [c.covers for c in a_cases] == [("R1",)]  # pruned, no call
    assert any("R2" in state.node(r).content.covers for r in state.test_cases("B"))
    for c in ("C",):
        for kind in (NodeKind.TEST_SET, NodeKind.CLUSTER_LABEL, NodeKind.RETRIEVAL):
            assert state.node(ref(kind, c)) == before.node(ref(kind, c))

    n1 = len(complete.requests)
    undone = await svc.command("P", CommandRequest(command=Undo()), actor="ayse")
    assert undone.accepted, undone
    await svc.wait_idle()

    assert complete.requests[n1:] == []
    after = svc.runtime("P").state
    assert hashes(after) == before_hashes
    assert after.node(ref(NodeKind.CLUSTER, "B")).content.pinned_members == ()
    assert svc.snapshot("P").jobs == ()
