import type { StudioApi } from "../api/client";
import type { SocketLike } from "../api/connection";
import type { CommandRequest, CommandResult, NodeView, ServerEvent, Snapshot } from "../types";

export function node(kind: NodeView["ref"]["kind"], key: string, content: Record<string, unknown> | null, extra: Partial<NodeView> = {}): NodeView {
  return { ref: { kind, key }, status: "fresh", pinned: false, origin: "generated", version: 1, content, ...extra };
}

export function testCase(id: string, covers: string[]): Record<string, unknown> {
  return {
    kind: "test_case",
    id,
    title: `Başlık ${id}`,
    covers,
    type: "Fonksiyonel",
    priority: "Yüksek",
    preconditions: "",
    test_inputs: "",
    assumptions: "",
    steps: [
      { no: 1, action: "Giriş yap", expected: "Giriş olur" },
      { no: 2, action: "Gönder", expected: "Gönderilir" },
    ],
  };
}

export function snapshot(seq = 5): Snapshot {
  return {
    project_id: "P",
    name: "Proje",
    seq,
    nodes: [
      node("project_card", "card", { kind: "project_card", text: "kart", methods: [{ name: "Test", criterion: "" }] }),
      node("requirement", "R1", { kind: "requirement", id: "R1", text: "Birinci gereksinim", language: "tr", source: "" }),
      node("requirement", "R2", { kind: "requirement", id: "R2", text: "İkinci gereksinim", language: "tr", source: "" }),
      node("requirement", "R3", { kind: "requirement", id: "R3", text: "Üçüncü gereksinim", language: "tr", source: "" }),
      node("method", "R1", { kind: "method", methods: ["Test"], rationale: "" }),
      node("cluster", "A", { kind: "cluster", members: ["R1", "R2"], pinned_members: [] }),
      node("cluster", "B", { kind: "cluster", members: ["R3"], pinned_members: [] }),
      node("cluster_label", "A", { kind: "cluster_label", name: "Giriş", rationale: "Girişle ilgili" }),
      node("cluster_label", "B", { kind: "cluster_label", name: "Rapor", rationale: "" }),
      node("test_set", "A", { kind: "test_set", case_keys: ["A:TC-1"] }),
      node("test_case", "A:TC-1", testCase("TC-1", ["R1"]), { version: 2 }),
    ],
    stages: [
      { stage: "cluster_label", mode: "auto", fresh: 2, stale: 0, running: 0, failed: 0, waiting_approval: false },
      { stage: "test_case", mode: "auto", fresh: 1, stale: 0, running: 0, failed: 0, waiting_approval: false },
    ],
    jobs: [],
    matrix: [],
    locks: {},
  };
}

export function ev(seq: number, type: ServerEvent["type"], payload: Record<string, unknown>, actor = "baska"): ServerEvent {
  return { seq, project_id: "P", type, actor, payload };
}

export class FakeSocket implements SocketLike {
  static instances: FakeSocket[] = [];
  onopen: SocketLike["onopen"] = null;
  onmessage: SocketLike["onmessage"] = null;
  onclose: SocketLike["onclose"] = null;
  onerror: SocketLike["onerror"] = null;
  sent: string[] = [];
  closed = false;
  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
  }
  open() {
    this.onopen?.();
  }
  push(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  drop() {
    this.onclose?.();
  }
}

export function fakeApi(overrides: Partial<StudioApi> = {}): StudioApi & { commands: CommandRequest[] } {
  const commands: CommandRequest[] = [];
  const api: StudioApi & { commands: CommandRequest[] } = {
    commands,
    listProjects: async () => [{ id: "P", name: "Proje" }],
    createProject: async () => snapshot(),
    snapshot: async () => snapshot(),
    command: async (_id, req): Promise<CommandResult> => {
      commands.push(req);
      return { accepted: true, seq: 6, reason: "", current_versions: {} };
    },
    lock: async () => true,
    matrixUrl: (id) => `/projects/${id}/matrix.xlsx`,
    ...overrides,
  };
  return api;
}

export const memoryStorage = () => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
};
