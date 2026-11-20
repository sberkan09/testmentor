import json

import pytest

from eval.golden import load_golden
from eval.judge import Verdict, judge_prompt, judge_run, reference_checks
from services.judge_client import JudgeClient, JudgeReply, JudgeSettings, JudgeUnavailable


class FakeJudge(JudgeClient):
    def __init__(self, settings):
        self.settings = settings
        self.calls = 0

    async def judge(self, system, user, output):
        self.calls += 1
        n = user.count("\n[")
        checks = [{"no": i, "matched": i == 1, "evidence": ""} for i in range(1, n + 1)]
        v = Verdict(checks=checks, invented=[], boundary_ok=True, ambiguity_flagged=False)
        return JudgeReply(parsed=v, stop_reason="end_turn", usage={})


def settings(tmp_path):
    return JudgeSettings(
        model="m",
        effort="medium",
        max_tokens=100,
        rubric_version="r1",
        concurrency=2,
        api_key_env="X_TEST_KEY",
        cache_dir=str(tmp_path / "cache"),
    )


def make_run(tmp_path, golden):
    run = tmp_path / "run"
    run.mkdir()
    p = golden.projects[0]
    tests = [
        {"title": "t", "covers": [r.id], "steps": [{"no": 1, "action": "a", "expected": "e"}]}
        for r in p.requirements
    ]
    rec = {"repeat": 0, "type": "project", "project": p.key, "test_cases": tests}
    (run / "outputs.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return run


async def test_judge_run_scores_and_caches(tmp_path, monkeypatch):
    import eval.judge as j

    monkeypatch.setattr(j, "ROOT", tmp_path)
    golden = load_golden(projects=["AI"])
    run = make_run(tmp_path, golden)
    judge = FakeJudge(settings(tmp_path))
    s1 = await judge_run(run, judge, golden)
    checks = reference_checks(golden)
    with_checks = [r.id for r in golden.projects[0].requirements if r.id in checks]
    assert judge.calls == len(with_checks)
    assert s1["check_recall"] == round(
        len(with_checks) / sum(len(checks[r]) for r in with_checks), 4
    )
    assert s1["stats"]["called"] == len(with_checks)
    s2 = await judge_run(run, judge, golden)
    assert judge.calls == len(with_checks) and s2["stats"]["cached"] == len(with_checks)
    assert (run / "judge.jsonl").exists()


def test_prompt_contains_numbered_checks():
    golden = load_golden(projects=["KMU"])
    checks = reference_checks(golden)["KMU-001"]
    req = golden.projects[0].raw["requirements"][0]
    text = judge_prompt(req, checks, [])
    assert "[1] " in text and "(none)" in text and req["text"] in text


def test_missing_key_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("X_TEST_KEY", raising=False)
    with pytest.raises(JudgeUnavailable):
        JudgeClient(settings(tmp_path))


def test_rubric_version_selects_text():
    from eval.judge import RUBRICS

    assert set(RUBRICS) >= {"r1", "r2"} and RUBRICS["r2"].startswith(RUBRICS["r1"])
    assert "train" not in RUBRICS["r2"].lower()  # domain-neutral example


def test_paired_bootstrap(tmp_path):
    """eval.paired: requirements scored in both runs, repeats pooled, difference with interval."""
    import json

    from eval.paired import load, paired

    def write(d, rows):
        d.mkdir()
        (d / "judge.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    row = lambda rid, m, rep=0: {
        "requirement": rid,
        "matched": m,
        "checks": 4,
        "repeat": rep,
        "unscored": None,
    }  # noqa: E731
    write(
        tmp_path / "a", [row("R1", 4), row("R2", 2), row("R1", 2, 1), row("R2", 2, 1), row("R3", 1)]
    )
    write(tmp_path / "b", [row("R1", 2), row("R2", 2)])
    out = paired(load(tmp_path / "a"), load(tmp_path / "b"), samples=200)
    assert out["requirements"] == 2  # R3 only in a
    assert out["new"] == 0.625 and out["baseline"] == 0.5 and out["difference"] == 0.125
    assert out["low"] <= out["difference"] <= out["high"]
