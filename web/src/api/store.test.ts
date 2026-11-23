import { beforeEach, describe, expect, it } from "vitest";
import { FakeSocket, ev, fakeApi, memoryStorage, node, snapshot } from "../test/fixtures";
import type { CommandResult } from "../types";
import { applyPending } from "./optimistic";
import { clusters } from "./selectors";
import { createStudioStore, rejectionText } from "./store";

beforeEach(() => {
  FakeSocket.instances = [];
});

function setup(apiOverrides = {}) {
  const api = fakeApi(apiOverrides);
  const store = createStudioStore({ api, socketFactory: (u) => new FakeSocket(u), storage: memoryStorage() });
  store.getState().setUser("ayse");
  return { api, store };
}

const members = (store: ReturnType<typeof setup>["store"], cluster: string) => {
  const s = store.getState();
  const view = applyPending(s.server!, s.pending);
  return clusters(view).find((c) => c.key === cluster)?.members.map((m) => m.id);
};

describe("iyimser güncelleme", () => {
  it("taşıma hemen görünür, sunucu olayıyla teyit edilince bekleyen yama düşer", async () => {
    const { store } = setup();
    await store.getState().openProject("P");
    expect(members(store, "B")).toEqual(["R3"]);

    const done = store.getState().send({ type: "move_requirement", requirement: "R1", to_cluster: "B" });
    expect(members(store, "B")).toEqual(["R1", "R3"]); // yanıt gelmeden
    expect(members(store, "A")).toEqual(["R2"]);
    await done;
    expect(store.getState().pending).toHaveLength(1); // kabul edildi ama olay (seq 6) henüz gelmedi

    store.getState().receiveEvent(ev(6, "node_updated", { node: node("cluster", "A", { kind: "cluster", members: ["R2"], pinned_members: [] }, { version: 2 }) }));
    store.getState().receiveEvent(ev(7, "node_updated", { node: node("cluster", "B", { kind: "cluster", members: ["R1", "R3"], pinned_members: [] }, { version: 2 }) }));
    expect(store.getState().pending).toHaveLength(0);
    expect(members(store, "B")).toEqual(["R1", "R3"]);
    expect(members(store, "A")).toEqual(["R2"]);
  });

  it("reddedilen komut geri alınır ve bildirim gösterilir", async () => {
    const rejected: CommandResult = { accepted: false, seq: 5, reason: "locked", current_versions: {} };
    const { store } = setup({ command: async () => rejected });
    await store.getState().openProject("P");
    const res = await store.getState().send({ type: "move_requirement", requirement: "R1", to_cluster: "B" });
    expect(res?.accepted).toBe(false);
    expect(store.getState().pending).toHaveLength(0);
    expect(members(store, "A")).toEqual(["R1", "R2"]);
    expect(store.getState().notices[0]?.text).toBe(rejectionText("locked"));
  });

  it("sürüm çakışmasında güncel durumu yeniden çeker; sunucu kazanır", async () => {
    const fresh = snapshot(8);
    fresh.nodes = fresh.nodes.map((n) =>
      n.ref.kind === "cluster_label" && n.ref.key === "A" ? { ...n, version: 3, content: { kind: "cluster_label", name: "Başkasının adı", rationale: "" } } : n,
    );
    let calls = 0;
    const { store, api } = setup({
      snapshot: async () => (calls++ === 0 ? snapshot(5) : fresh),
      command: async () => ({ accepted: false, seq: 8, reason: "version_conflict", current_versions: { "cluster_label:A": 3 } }),
    });
    await store.getState().openProject("P");
    await store.getState().send({ type: "rename_cluster", cluster: "A", name: "Benim adım" });
    await new Promise((r) => setTimeout(r, 0));
    const view = applyPending(store.getState().server!, store.getState().pending);
    expect(clusters(view).find((c) => c.key === "A")?.name).toBe("Başkasının adı");
    expect(store.getState().server?.seq).toBe(8);
    expect(api).toBeDefined();
  });

  it("komut sürüm bilgisiyle gider (expected_versions)", async () => {
    const { store, api } = setup();
    await store.getState().openProject("P");
    const content = { ...(snapshot().nodes.find((n) => n.ref.kind === "test_case")?.content as object) } as never;
    await store.getState().send({ type: "edit_test_case", case: "A:TC-1", content });
    expect(api.commands[0]?.expected_versions).toEqual({ "test_case:A:TC-1": 2 });
  });

  it("ağ hatasında yama düşer", async () => {
    const { store } = setup({
      command: async () => {
        throw new Error("ağ");
      },
    });
    await store.getState().openProject("P");
    await store.getState().send({ type: "pin", node: { kind: "test_case", key: "A:TC-1" } });
    expect(store.getState().pending).toHaveLength(0);
    expect(store.getState().notices).toHaveLength(1);
  });
});

describe("yeniden bağlanma", () => {
  it("kopma sırasında kaçan olaylar yeniden bağlanınca gelir; durum sunucuyla aynı olur", async () => {
    const { store } = setup();
    await store.getState().openProject("P");
    const first = FakeSocket.instances[0] as FakeSocket;
    expect(first.url).toContain("after=5");
    first.open();
    first.push(ev(6, "node_removed", { ref: { kind: "test_case", key: "A:TC-1" } }));
    expect(store.getState().server?.seq).toBe(6);
    first.drop();
    await new Promise((r) => setTimeout(r, 600));
    const second = FakeSocket.instances[1] as FakeSocket;
    expect(second.url).toContain("after=6");
    second.open();
    second.push(ev(7, "node_updated", { node: node("cluster_label", "B", { kind: "cluster_label", name: "Yeni", rationale: "" }, { version: 2 }) }));
    second.push(ev(8, "lock_changed", { ref: "x", user: "ali" }));
    const s = store.getState().server!;
    expect(s.seq).toBe(8);
    expect(s.nodes["test_case:A:TC-1"]).toBeUndefined();
    expect(s.nodes["cluster_label:B"]?.content?.["name"]).toBe("Yeni");
  });

  it("olaylar halkadan düştüyse gelen snapshot mesajı durumu değiştirir", async () => {
    const { store } = setup();
    await store.getState().openProject("P");
    const s = FakeSocket.instances[0] as FakeSocket;
    s.open();
    s.push({ type: "snapshot", snapshot: snapshot(40) });
    expect(store.getState().server?.seq).toBe(40);
  });

  it("başka projenin olayını yok sayar", async () => {
    const { store } = setup();
    await store.getState().openProject("P");
    store.getState().receiveEvent({ ...ev(6, "node_removed", { ref: { kind: "cluster", key: "A" } }), project_id: "BASKA" });
    expect(store.getState().server?.seq).toBe(5);
  });
});

describe("kullanıcı adı", () => {
  it("saklanır ve yeni mağazada okunur", () => {
    const storage = memoryStorage();
    const api = fakeApi();
    createStudioStore({ api, storage }).getState().setUser("  mehmet ");
    expect(createStudioStore({ api, storage }).getState().user).toBe("mehmet");
  });
});
