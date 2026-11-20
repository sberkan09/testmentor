"""The pod watchdog must delete the pod without the controlling session (no real API call)."""

import os
import stat
import subprocess
import time

import pytest

from scripts.infra_render import render_download_script, render_pod_script, watchdog_lines

FAST = {"idle_minutes": 2, "grace_minutes": 0, "gpu_util_idle_below": 5}


def stub_bin(tmp_path, gpu_util: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.txt"
    # python3 stub: record that a self-delete was attempted, succeed.
    (bin_dir / "python3").write_text(f"#!/bin/bash\ncat > /dev/null\necho delete >> {calls}\n")
    (bin_dir / "nvidia-smi").write_text(f"#!/bin/bash\necho {gpu_util}\n")
    for f in bin_dir.iterdir():
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return bin_dir, calls


def run(tmp_path, gpu_util, deadline_offset, seconds):
    bin_dir, calls = stub_bin(tmp_path, gpu_util)
    log = tmp_path / "wd.log"
    script = "\n".join(watchdog_lines(log=str(log), interval_s=1, settings=FAST)) + "\nwait\n"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "WATCHDOG_DEADLINE": str(int(time.time()) + deadline_offset) if deadline_offset else "0",
    }
    proc = subprocess.Popen(["bash", "-c", script], env=env, start_new_session=True)
    time.sleep(seconds)
    os.killpg(proc.pid, 9)
    return (calls.read_text() if calls.exists() else ""), log.read_text()


def test_deadline_triggers_self_delete(tmp_path):
    calls, log = run(tmp_path, gpu_util="90", deadline_offset=2, seconds=5)
    assert "delete" in calls and "en uzun ömür doldu" in log


def test_idle_gpu_triggers_self_delete(tmp_path):
    calls, log = run(tmp_path, gpu_util="0", deadline_offset=0, seconds=5)
    assert "delete" in calls and "boşta" in log


def test_busy_gpu_without_deadline_keeps_pod(tmp_path):
    calls, log = run(tmp_path, gpu_util="95", deadline_offset=0, seconds=4)
    assert calls == "" and "başladı" in log


@pytest.mark.parametrize("engine", ["vllm", "sglang"])
def test_every_pod_script_has_watchdog(engine):
    script = render_pod_script(engine, "qwen3.8-27b")
    assert "self_delete()" in script and "RUNPOD_POD_ID" in script
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)


def test_download_pod_deletes_itself_when_done():
    script = render_download_script()
    assert script.index("[download] DONE") < script.index('self_delete "indirme bitti"')
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)


def test_batch_always_deletes_pod(monkeypatch, tmp_path):
    import eval.batch as b

    monkeypatch.setattr(b, "ROOT", tmp_path)
    calls = []

    def runner(cmd):
        calls.append(cmd)
        if "eval.run" in cmd:
            raise RuntimeError("deney çöktü")
        return 0

    with pytest.raises(RuntimeError):
        b.run_batch({"steps": [{"experiment": "a"}, {"experiment": "b"}]}, runner=runner)
    assert calls[-1][-1] == "down"  # down ran despite the crash


def test_batch_step_failure_continues_and_deletes(monkeypatch, tmp_path):
    import eval.batch as b

    monkeypatch.setattr(b, "ROOT", tmp_path)
    calls = []

    def runner(cmd):
        calls.append(cmd)
        return 1 if "wait" in cmd else 0

    res = b.run_batch(
        {"steps": [{"experiment": "a"}, {"experiment": "b", "model": "m"}]}, runner=runner
    )
    assert res == {"a": "sunucu hazır olmadı", "b": "sunucu hazır olmadı", "_down": "pod silindi"}
    assert "--model" in calls[2] and "reconfigure" in calls[2]


def test_pod_without_deadline_is_refused(tmp_path, monkeypatch):
    import scripts.runpod as rp
    import scripts.runpod_state as st

    monkeypatch.setattr(st, "ENV_PATH", tmp_path / ".env")
    with pytest.raises(ValueError):
        rp.pod_body("vllm", "qwen3.8-27b", "vol", False)
    body = rp.pod_body("vllm", "qwen3.8-27b", "vol", False, deadline=1234567890)
    assert body["env"]["WATCHDOG_DEADLINE"] == "1234567890"
    assert "WATCHDOG_DEADLINE" in rp.download_body("vol")["env"]


def test_watchdog_cannot_be_disabled(monkeypatch):
    import scripts.runpod as rp

    real = rp.load_infra
    monkeypatch.setattr(rp, "load_infra", lambda: real() | {"watchdog": {"enabled": False}})
    with pytest.raises(SystemExit):
        rp.watchdog_deadline(2)
