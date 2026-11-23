import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { useActions, useApi, useView } from "../context";
import type { KbDocumentView } from "../types";

const ACCEPT = ".txt,.md,.markdown,.pdf";

function when(t: number): string {
  if (!t) return "";
  return new Date(t * 1000).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

/** Knowledge base documents of the open project (paket 10): list, upload, remove. The list is
 *  not part of the snapshot; it is read again whenever the project's `kb_index` node changes
 *  (an upload by anyone), so every open tab stays current. */
export function DocumentsView() {
  const state = useView();
  const api = useApi();
  const { notify } = useActions();
  const projectId = state?.projectId ?? "";
  const indexVersion = state?.nodes["kb_index:index"]?.version ?? 0;
  const [docs, setDocs] = useState<KbDocumentView[] | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      setDocs(await api.listDocuments(projectId));
    } catch (e) {
      setDocs([]);
      notify("error", `Belgeler yüklenemedi: ${(e as Error).message}`);
    }
  }, [api, projectId, notify]);

  useEffect(() => {
    void refresh();
  }, [refresh, indexVersion]);

  async function upload(files: FileList | null) {
    const list = Array.from(files ?? []);
    if (!projectId || list.length === 0) return;
    setBusy(true);
    for (const file of list) {
      try {
        const res = await api.uploadDocument(projectId, file);
        notify("info", `${res.document.name} eklendi (${res.document.chunks} parça). Arama düğümleri yeniden denetleniyor.`);
      } catch (e) {
        notify("error", e instanceof ApiError ? `${file.name} eklenemedi: ${e.message}` : `${file.name} eklenemedi.`);
      }
    }
    setBusy(false);
    if (input.current) input.current.value = "";
    await refresh();
  }

  async function remove(doc: KbDocumentView) {
    if (!projectId) return;
    try {
      await api.removeDocument(projectId, doc.id);
      notify("info", `${doc.name} kaldırıldı.`);
    } catch (e) {
      notify("error", `${doc.name} kaldırılamadı: ${(e as Error).message}`);
    }
    await refresh();
  }

  if (!state) return null;
  return (
    <>
      <div className="canvas-toolbar" data-testid="documents-toolbar">
        <div className="summary">
          <span>
            <strong data-testid="documents-count">{docs?.length ?? 0}</strong> belge
          </span>
          <span>Belgeler parçalara bölünür; her öbek için en ilgili parçalar test üretimine girer.</span>
        </div>
        <div className="spacer" />
        <button className="btn primary" data-testid="document-upload" disabled={busy} onClick={() => input.current?.click()}>
          {busy ? "Yükleniyor…" : "+ Belge yükle"}
        </button>
        <input ref={input} data-testid="document-file" type="file" accept={ACCEPT} multiple hidden onChange={(e) => void upload(e.target.files)} />
      </div>
      <div className="canvas-body">
        {docs !== null && docs.length === 0 ? (
          <div className="empty" data-testid="documents-empty">
            <strong>Henüz belge yok</strong>
            <span>Şartname, mevzuat ya da standart metni yükle: .txt, .md ya da metin katmanlı .pdf.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="matrix" data-testid="documents-table">
              <thead>
                <tr>
                  <th>Belge</th>
                  <th>Parça</th>
                  <th>Ekleyen</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(docs ?? []).map((d) => (
                  <tr key={d.id} data-testid={`document-${d.id}`}>
                    <td>
                      <strong>{d.name}</strong>
                      <div className="rtext">
                        <code>{d.id}</code>
                      </div>
                    </td>
                    <td data-testid={`document-chunks-${d.id}`}>{d.chunks}</td>
                    <td>
                      {d.added_by}
                      <div className="rtext">{when(d.added_at ?? 0)}</div>
                    </td>
                    <td>
                      <button className="btn small" data-testid={`document-remove-${d.id}`} onClick={() => void remove(d)}>
                        Kaldır
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
