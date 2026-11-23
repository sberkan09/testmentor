import { describe, expect, it } from "vitest";
import { ev, node, snapshot, testCase } from "../test/fixtures";
import { applyEvent, fromSnapshot } from "./state";
import { clusters, matrixRows } from "./selectors";

const base = () => fromSnapshot(snapshot(5));

describe("applyEvent", () => {
  it("node_updated yeni sürümü yazar, sürüm geçmişine ekler", () => {
    const updated = node("cluster_label", "A", { kind: "cluster_label", name: "Yeni ad", rationale: "" }, { version: 2, origin: "edited" });
    const s = applyEvent(base(), ev(6, "node_updated", { node: updated }, "ali"));
    expect(s.seq).toBe(6);
    expect(s.nodes["cluster_label:A"]?.content?.["name"]).toBe("Yeni ad");
    expect(s.history["cluster_label:A"]?.at(-1)).toMatchObject({ version: 2, actor: "ali", origin: "edited" });
  });

  it("tekrar gelen olayı (seq küçük ya da eşit) yok sayar", () => {
    const s0 = base();
    const dup = applyEvent(s0, ev(5, "node_removed", { ref: { kind: "cluster", key: "A" } }));
    expect(dup).toBe(s0);
  });

  it("node_removed düğümü siler", () => {
    const s = applyEvent(base(), ev(6, "node_removed", { ref: { kind: "test_case", key: "A:TC-1" } }));
    expect(s.nodes["test_case:A:TC-1"]).toBeUndefined();
  });

  it("job_progress metni biriktirir, seq'i ilerletmez, node_updated ile temizlenir", () => {
    const job = { id: "j1", node: { kind: "cluster_label", key: "A" }, priority: "P2", state: "running" };
    let s = applyEvent(base(), ev(0, "job_progress", { job, text: "Mer" }));
    s = applyEvent(s, ev(0, "job_progress", { job, text: "haba" }));
    expect(s.progress["cluster_label:A"]).toBe("Merhaba");
    expect(s.seq).toBe(5);
    s = applyEvent(s, ev(6, "node_updated", { node: node("cluster_label", "A", { kind: "cluster_label", name: "X", rationale: "" }, { version: 2 }) }));
    expect(s.progress["cluster_label:A"]).toBeUndefined();
  });

  it("job_started ve job_done iş listesini günceller", () => {
    const job = { id: "j1", node: { kind: "test_case", key: "A:TC-1" }, priority: "P0", state: "queued" };
    let s = applyEvent(base(), ev(6, "job_started", { job }));
    expect(s.jobs["j1"]?.state).toBe("running");
    s = applyEvent(s, ev(7, "job_done", { job }));
    expect(s.jobs["j1"]).toBeUndefined();
  });

  it("başlayan ve biten iş, snapshot'taki aynı düğümün sıradaki kaydını da siler", () => {
    const s0 = base();
    const queued = { id: "q:test_set:A", node: { kind: "test_set", key: "A" }, priority: "P2", state: "queued" };
    const withQueued = { ...s0, jobs: { ...s0.jobs, [queued.id]: queued } } as typeof s0;
    const job = { id: "job-7", node: { kind: "test_set", key: "A" }, priority: "P2", state: "running" };
    let s = applyEvent(withQueued, ev(6, "job_started", { job, nodes: ["test_set:A"] }));
    expect(s.jobs["q:test_set:A"]).toBeUndefined();
    expect(s.jobs["job-7"]?.state).toBe("running");
    s = applyEvent({ ...s, jobs: { ...s.jobs, [queued.id]: queued } } as typeof s, ev(7, "job_done", { job, nodes: ["test_set:A"] }));
    expect(Object.keys(s.jobs)).toEqual([]);
  });

  it("lock_changed kilidi koyar ve kaldırır", () => {
    let s = applyEvent(base(), ev(6, "lock_changed", { ref: "test_case:A:TC-1", user: "ali" }));
    expect(s.locks["test_case:A:TC-1"]).toBe("ali");
    s = applyEvent(s, ev(7, "lock_changed", { ref: "test_case:A:TC-1", user: null }));
    expect(s.locks["test_case:A:TC-1"]).toBeUndefined();
  });

  it("command_applied aşama modunu ve onayı yansıtır", () => {
    let s = applyEvent(base(), ev(6, "command_applied", { command: { type: "set_stage_mode", stage: "test_case", mode: "approval" } }));
    expect(s.stages.find((g) => g.stage === "test_case")?.mode).toBe("approval");
    s = applyEvent(s, ev(7, "stage_waiting_approval", { stage: "test_case" }));
    expect(s.stages.find((g) => g.stage === "test_case")?.waiting_approval).toBe(true);
    s = applyEvent(s, ev(8, "command_applied", { command: { type: "approve_stage", stage: "test_case" } }));
    expect(s.stages.find((g) => g.stage === "test_case")?.waiting_approval).toBe(false);
  });
});

describe("türetilmiş görünüm", () => {
  it("öbekleri ad ve üyelerle, matrisi kapsama ile kurar", () => {
    const s = base();
    const cl = clusters(s);
    expect(cl.map((c) => c.name)).toEqual(["Giriş", "Rapor"]);
    expect(cl[0]?.members.map((m) => m.id)).toEqual(["R1", "R2"]);
    const rows = matrixRows(s);
    expect(rows.find((r) => r.requirement_id === "R1")).toMatchObject({ covered: true, test_case_keys: ["A:TC-1"], cluster: "A", methods: ["Test"] });
    expect(rows.find((r) => r.requirement_id === "R2")?.covered).toBe(false);
  });

  it("yeni test durumu olayı kapsamayı günceller", () => {
    const s = applyEvent(base(), ev(6, "node_created", { node: node("test_case", "A:TC-2", testCase("TC-2", ["R2"])) }));
    expect(matrixRows(s).find((r) => r.requirement_id === "R2")?.covered).toBe(true);
  });
});
