"""The shared fake model drives every stage to a fresh state (used by paket 4–8 tests)."""

from core.invalidation import analyze
from core.nodes import NodeKind
from services.fake_llm import FakeComplete, FakeEmbed
from tests.stages.helpers import drive, project


async def test_fake_model_produces_every_stage():
    complete = FakeComplete()
    out = await drive(
        project(),
        complete,
        real=set(NodeKind)
        - {
            NodeKind.REQUIREMENT,
            NodeKind.PROJECT_CARD,
            NodeKind.KB_INDEX,
            NodeKind.CLUSTER,
            NodeKind.TEST_CASE,
        },
        embed=FakeEmbed(),
    )
    assert not analyze(out.state).stale
    assert not out.failed()
    assert {r.stage for r in complete.requests} == {
        NodeKind.METHOD,
        NodeKind.CLUSTER_LABEL,
        NodeKind.TEST_SET,
    }


async def test_fake_embed_similarity():
    e = FakeEmbed()
    a, b, c = await e(
        ["parola sıfırlama bağlantısı", "parola sıfırlama süresi", "rapor ekranı açılışı"]
    )

    def dot(x, y):
        return sum(p * q for p, q in zip(x, y, strict=True))

    assert dot(a, b) > dot(a, c)
