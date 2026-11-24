"""Credit protection (23 Nov 2026): a pod that never becomes ready is deleted by `wait`.

The host of one pod could not mount the network volume: the container never started, so the
watchdog inside it never ran and nothing would have deleted the billing pod."""

from __future__ import annotations

import argparse

import httpx

import scripts.runpod as rp_mod


class _NeverReady:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        raise httpx.ConnectError("404 from the proxy: nothing listens")


def _setup(monkeypatch):
    monkeypatch.setattr(
        rp_mod,
        "read_state",
        lambda: {"pod": {"id": "p1", "llm_port": 8000, "created_monotonic_hint": 0}},
    )
    monkeypatch.setattr(rp_mod, "ensure_env_secret", lambda name: "x")
    monkeypatch.setattr(rp_mod.httpx, "Client", _NeverReady)
    monkeypatch.setattr(rp_mod.time, "sleep", lambda s: None)
    downs = []
    monkeypatch.setattr(rp_mod, "cmd_down", lambda rp, args: downs.append("down") or 0)
    return downs


def test_wait_timeout_deletes_the_pod(monkeypatch):
    downs = _setup(monkeypatch)
    code = rp_mod.cmd_wait(object(), argparse.Namespace(timeout=0.01, keep_on_timeout=False))
    assert code == 1 and downs == ["down"]


def test_keep_on_timeout_leaves_it(monkeypatch):
    downs = _setup(monkeypatch)
    code = rp_mod.cmd_wait(object(), argparse.Namespace(timeout=0.01, keep_on_timeout=True))
    assert code == 1 and downs == []
