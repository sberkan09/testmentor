import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { createStudioStore } from "../api/store";
import { StudioProvider } from "../context";
import { FakeSocket, fakeApi, memoryStorage, node, snapshot } from "../test/fixtures";

beforeEach(() => {
  FakeSocket.instances = [];
});
afterEach(cleanup);

function mount(apiOverrides = {}) {
  const api = fakeApi(apiOverrides);
  const store = createStudioStore({ api, socketFactory: (u) => new FakeSocket(u), storage: memoryStorage() });
  store.getState().setUser("ayse");
  render(
    <StudioProvider store={store} api={api}>
      <App />
    </StudioProvider>,
  );
  return { api, store };
}

async function openProject() {
  const ctx = mount();
  await userEvent.click(await screen.findByTestId("project-P"));
  await screen.findByTestId("studio");
  return ctx;
}

describe("içe alma", () => {
  it("dosyayı okur, kolonları tahmin eder, eşlemeyle yükler", async () => {
    const createProject = vi.fn(async () => snapshot());
    mount({ createProject });
    await userEvent.click(await screen.findByTestId("import-open"));
    const csv = 'id,language,text\nR1,tr,"Birinci, gereksinim"\nR2,tr,İkinci\n';
    await userEvent.upload(screen.getByTestId("import-file"), new File([csv], "set.csv", { type: "text/csv" }));
    await screen.findByTestId("import-preview");
    expect(screen.getByTestId("map-text")).toHaveValue("text");
    expect(screen.getByTestId("map-id")).toHaveValue("id");
    expect(screen.getByText("Birinci, gereksinim")).toBeInTheDocument();
    await userEvent.type(screen.getByTestId("import-key"), "KDH");
    await userEvent.click(screen.getByTestId("import-submit"));
    await waitFor(() => expect(createProject).toHaveBeenCalled());
    const calls = createProject.mock.calls as unknown as [{ name: string; key: string; mapping: Record<string, string | null> }, File][];
    const meta = calls[0]?.[0];
    expect(meta).toMatchObject({ name: "set", key: "KDH", mapping: { text: "text", id: "id", language: "language", source: null } });
    await screen.findByTestId("studio");
  });
});

describe("öbek görünümü ve denetçi", () => {
  it("öbek kartlarını, çipleri ve kapsanmamış rozetini gösterir", async () => {
    await openProject();
    expect(screen.getByTestId("cluster-A")).toHaveTextContent("Giriş");
    expect(screen.getByTestId("chip-R1")).toBeInTheDocument();
    expect(screen.getByTestId("uncovered-R2")).toBeInTheDocument(); // R2'yi kapsayan test yok
    expect(screen.queryByTestId("uncovered-R1")).toBeNull();
  });

  it("gereksinimi seçince denetçi açılır; öbek seçiciyle taşıma komutu gider", async () => {
    const { api } = await openProject();
    await userEvent.click(screen.getByTestId("chip-R1"));
    expect(await screen.findByTestId("inspector-requirement")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByTestId("req-cluster"), "B");
    expect(api.commands.at(-1)?.command).toEqual({ type: "move_requirement", requirement: "R1", to_cluster: "B" });
    // iyimser: çip hemen B kartında
    expect(screen.getByTestId("cluster-B")).toContainElement(screen.getByTestId("chip-R1"));
  });

  it("klavyede M tuşu taşıma penceresini açar", async () => {
    const { api } = await openProject();
    screen.getByTestId("chip-R2").focus();
    await userEvent.keyboard("m");
    await userEvent.selectOptions(await screen.findByTestId("move-target"), "B");
    await userEvent.click(screen.getByTestId("move-confirm"));
    expect(api.commands.at(-1)?.command).toMatchObject({ type: "move_requirement", requirement: "R2", to_cluster: "B" });
  });

  it("test durumunun adımları ayrı alandır; düzenleyip kaydedince komut tam içerikle gider", async () => {
    const { api } = await openProject();
    await userEvent.click(screen.getByTestId("case-A:TC-1"));
    const expected = await screen.findByTestId("step-1-expected");
    expect(screen.getByTestId("step-1-action")).toHaveValue("Giriş yap");
    expect(screen.getByTestId("save")).toBeDisabled();
    await userEvent.clear(expected);
    await userEvent.type(expected, "Yeni beklenen");
    await userEvent.click(screen.getByTestId("save"));
    const cmd = api.commands.at(-1)?.command;
    expect(cmd).toMatchObject({ type: "edit_test_case", case: "A:TC-1" });
    if (cmd?.type !== "edit_test_case") throw new Error("komut tipi");
    expect(cmd.content.steps[0]).toEqual({ no: 1, action: "Giriş yap", expected: "Yeni beklenen" });
    expect(cmd.content.steps[1]?.action).toBe("Gönder");
  });

  it("sabitle düğmesi pin komutu yollar ve iyimser olarak iğne gösterir", async () => {
    const { api } = await openProject();
    await userEvent.click(screen.getByTestId("case-A:TC-1"));
    await userEvent.click(await screen.findByTestId("pin"));
    expect(api.commands.at(-1)?.command).toEqual({ type: "pin", node: { kind: "test_case", key: "A:TC-1" } });
    expect(await screen.findByTestId("pinned-pill")).toBeInTheDocument();
  });
});

describe("matris görünümü", () => {
  it("kapsama oranını, uyarı alanını ve xlsx bağlantısını gösterir; filtre çalışır", async () => {
    await openProject();
    await userEvent.click(screen.getByTestId("view-matrix"));
    expect(await screen.findByTestId("matrix-covered")).toHaveTextContent("1");
    expect(screen.getByTestId("matrix-coverage")).toHaveTextContent("%33");
    expect(screen.getByTestId("matrix-download")).toHaveAttribute("href", "/projects/P/matrix.xlsx");
    expect(screen.getByTestId("covered-R1")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByTestId("filter-coverage"), "uncovered");
    expect(screen.queryByTestId("row-R1")).toBeNull();
    expect(screen.getByTestId("row-R2")).toBeInTheDocument();
  });
});

describe("kilit", () => {
  it("başkasının kilitlediği öğe düzenlenemez", async () => {
    const { store } = await openProject();
    await userEvent.click(screen.getByTestId("case-A:TC-1"));
    await screen.findByTestId("tc-title");
    store.getState().receiveEvent({ seq: 6, project_id: "P", type: "lock_changed", actor: "ali", payload: { ref: "test_case:A:TC-1", user: "ali" } });
    expect(await screen.findByTestId("lock-banner")).toHaveTextContent("ali");
    expect(screen.getByTestId("tc-title")).toBeDisabled();
  });
});

describe("bilgi havuzu (paket 10)", () => {
  it("öbek denetçisi arama düğümünün parça kimliklerini gösterir", async () => {
    const snap = snapshot();
    snap.nodes.push(
      node("retrieval", "A", { kind: "retrieval", passage_ids: ["politika.md#0@ab12cd34", "politika.md#3@ffee0011"], example_keys: [] }),
      node("retrieval", "B", { kind: "retrieval", passage_ids: [], example_keys: [] }),
    );
    mount({ snapshot: async () => snap });
    await userEvent.click(await screen.findByTestId("project-P"));
    await userEvent.click(await screen.findByTestId("cluster-name-A"));
    const chips = await screen.findAllByTestId("passage-id");
    expect(chips.map((c) => c.textContent)).toEqual(["politika.md#0", "politika.md#3"]);
    await userEvent.click(screen.getByTestId("cluster-name-B"));
    expect(await screen.findByTestId("passages-empty")).toBeInTheDocument();
  });

  it("Belgeler sekmesi listeler, yükler ve kaldırır", async () => {
    let docs = [{ id: "a.md", name: "a.md", chunks: 2, added_by: "ali", added_at: 0 }];
    const uploadDocument = vi.fn(async (_id: string, file: File) => {
      const doc = { id: file.name, name: file.name, chunks: 3, added_by: "ayse", added_at: 0 };
      docs = [...docs, doc];
      return { document: doc, seq: 7 };
    });
    const removeDocument = vi.fn(async () => {
      docs = docs.filter((d) => d.id !== "a.md");
      return { seq: 8 };
    });
    mount({ listDocuments: async () => docs, uploadDocument, removeDocument });
    await userEvent.click(await screen.findByTestId("project-P"));
    await userEvent.click(await screen.findByTestId("view-documents"));
    expect(await screen.findByTestId("document-a.md")).toHaveTextContent("ali");
    await userEvent.upload(screen.getByTestId("document-file"), new File(["# Başlık\n\nmetin"], "b.md", { type: "text/markdown" }));
    await waitFor(() => expect(uploadDocument).toHaveBeenCalledWith("P", expect.any(File)));
    expect(await screen.findByTestId("document-chunks-b.md")).toHaveTextContent("3");
    await userEvent.click(screen.getByTestId("document-remove-a.md"));
    await waitFor(() => expect(screen.queryByTestId("document-a.md")).toBeNull());
    expect(screen.getByTestId("documents-count")).toHaveTextContent("1");
  });
});
