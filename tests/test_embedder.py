import json

import httpx
import pytest

from services.embedder import Embedder, EmbeddingError
from services.settings import EmbeddingSettings


def settings(batch_size=2):
    return EmbeddingSettings(
        base_url="http://emb/v1", model="bge-m3", model_version="v1", batch_size=batch_size
    )


def transport(calls, status=200, shuffle=False):
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if status >= 400:
            return httpx.Response(status, text="boom")
        data = [
            {"index": i, "embedding": [float(len(t)), float(i)]}
            for i, t in enumerate(body["input"])
        ]
        if shuffle:
            data.reverse()
        return httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": 3}})

    return httpx.MockTransport(handle)


async def test_batches_and_preserves_order():
    calls = []
    async with Embedder(settings(), transport=transport(calls, shuffle=True)) as emb:
        out = await emb.embed(["a", "bb", "ccc", "dddd", "eeeee"])
    assert [len(c["input"]) for c in calls] == [2, 2, 1]
    assert all(c["model"] == "bge-m3" for c in calls)
    assert [v[0] for v in out.vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert out.model_version == "v1"
    assert out.prompt_tokens == 9


async def test_empty_input_makes_no_call():
    calls = []
    async with Embedder(settings(), transport=transport(calls)) as emb:
        out = await emb.embed([])
    assert out.vectors == [] and calls == []


async def test_http_error():
    async with Embedder(settings(), transport=transport([], status=500)) as emb:
        with pytest.raises(EmbeddingError):
            await emb.embed(["a"])
