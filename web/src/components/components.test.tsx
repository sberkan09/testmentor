import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { ApiError, createRestApi } from "../api/client";
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

describe("katman görünümü", () => {
  it("Katmanlar sekmesi 3B görünümü tembel yükler; çizim açılamazsa açıklama gösterir, 2B görünümler çalışır", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    await openProject();
    await userEvent.click(screen.getByTestId("view-layers"));
    expect(screen.getByTestId("view-layers")).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByTestId("layers-view", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByTestId("layers-uncovered")).toHaveTextContent("2");
    expect(await screen.findByTestId("layers-unsupported")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("view-clusters"));
    expect(await screen.findByTestId("cluster-A")).toBeInTheDocument();
    vi.restoreAllMocks();
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

describe("parolalı giriş (paket 10)", () => {
  function mountPassword(apiOverrides = {}) {
    const api = fakeApi({ authConfig: async () => ({ mode: "password" as const }), ...apiOverrides });
    const tokens = new Map<string, string>();
    const tokenStorage = { getItem: (k: string) => tokens.get(k) ?? null, setItem: (k: string, v: string) => void tokens.set(k, v), removeItem: (k: string) => void tokens.delete(k) };
    const store = createStudioStore({ api, socketFactory: (u) => new FakeSocket(u), storage: memoryStorage(), tokenStorage });
    render(
      <StudioProvider store={store} api={api}>
        <App />
      </StudioProvider>,
    );
    return { api, store, tokens };
  }

  it("başlık kipinde parola alanı yok", async () => {
    const api = fakeApi();
    const store = createStudioStore({ api, socketFactory: (u) => new FakeSocket(u), storage: memoryStorage() });
    render(
      <StudioProvider store={store} api={api}>
        <App />
      </StudioProvider>,
    );
    expect(await screen.findByTestId("user-name")).toBeInTheDocument();
    expect(screen.queryByTestId("user-password")).toBeNull();
  });

  it("yanlış parolada hata, doğru parolada jetonla projeler; WebSocket jetonu taşır", async () => {
    const login = vi.fn(async (user: string, password: string) => {
      if (password !== "parola123") throw new ApiError("kullanıcı adı ya da parola yanlış", 401);
      return { token: "jeton-1", user, expires_at: 0 };
    });
    const { store, tokens } = mountPassword({ login });
    await userEvent.type(await screen.findByTestId("user-name"), "ayşe");
    await userEvent.type(screen.getByTestId("user-password"), "yanlis");
    await userEvent.click(screen.getByTestId("user-submit"));
    expect(await screen.findByTestId("login-error")).toHaveTextContent("parola yanlış");
    await userEvent.type(screen.getByTestId("user-password"), "parola123");
    await userEvent.click(screen.getByTestId("user-submit"));
    await screen.findByTestId("projects-page");
    expect(store.getState().user).toBe("ayşe");
    expect(tokens.get("testmentor.token")).toBe("jeton-1");
    await userEvent.click(await screen.findByTestId("project-P"));
    await screen.findByTestId("studio");
    expect(FakeSocket.instances.at(-1)?.url).toContain("token=jeton-1");
    await userEvent.click(screen.getByTestId("logout"));
    expect(await screen.findByTestId("user-password")).toBeInTheDocument();
    expect(tokens.has("testmentor.token")).toBe(false);
  });

  it("401 cevabında giriş ekranına döner", async () => {
    const { store } = mountPassword();
    store.setState({ token: "eski", user: "ayşe" });
    await screen.findByTestId("projects-page");
    store.getState().logout(true);
    expect(await screen.findByTestId("user-password")).toBeInTheDocument();
    expect(await screen.findByText(/Oturumun sona erdi/)).toBeInTheDocument();
  });
});

describe("REST istemcisi kimliği", () => {
  it("jeton varsa Bearer, yoksa X-User; 401 kancayı çağırır; xlsx bağlantısı jetonu taşır", async () => {
    const seen: Record<string, string>[] = [];
    let status = 200;
    const fetchFn = (async (_url: string, init?: RequestInit) => {
      seen.push((init?.headers ?? {}) as Record<string, string>);
      return new Response(JSON.stringify([]), { status });
    }) as unknown as typeof fetch;
    let token: string | null = null;
    const onUnauthorized = vi.fn();
    const api = createRestApi(() => "Ayşe", fetchFn, { getToken: () => token, onUnauthorized });
    await api.listProjects();
    expect(seen.at(-1)).toEqual({ "X-User": "Ay%C5%9Fe" });
    expect(api.matrixUrl("P")).toBe("/projects/P/matrix.xlsx");
    token = "j t";
    await api.listProjects();
    expect(seen.at(-1)).toEqual({ Authorization: "Bearer j t" });
    expect(api.matrixUrl("P")).toBe("/projects/P/matrix.xlsx?token=j%20t");
    status = 401;
    await expect(api.listProjects()).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
});
