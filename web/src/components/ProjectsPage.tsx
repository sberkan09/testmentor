import { useEffect, useRef, useState } from "react";
import { useActions, useStudio } from "../context";
import { guessMapping, readTables, type SheetTables } from "../api/tabular";
import type { ImportRequest } from "../types";

export function UserGate() {
  const { setUser, login } = useActions();
  const passwordMode = useStudio((s) => s.authMode === "password");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <div className="overlay">
      <form
        className="dialog"
        style={{ width: 420 }}
        data-testid="user-gate"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!passwordMode) {
            setUser(name);
            return;
          }
          setBusy(true);
          setError("");
          const failed = await login(name, password);
          setBusy(false);
          if (failed) {
            setError(failed);
            setPassword("");
          }
        }}
      >
        <h2>{passwordMode ? "Giriş" : "Hoş geldin"}</h2>
        <p className="sub">Düzenlemelerin diğer kullanıcılara bu adla görünür.</p>
        <div className="field">
          <label htmlFor="user-name">Kullanıcı adı</label>
          <input id="user-name" data-testid="user-name" className="input" autoFocus autoComplete="username" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        {passwordMode && (
          <div className="field">
            <label htmlFor="user-password">Parola</label>
            <input
              id="user-password"
              data-testid="user-password"
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
        )}
        {error && (
          <div className="error-text" data-testid="login-error">
            {error}
          </div>
        )}
        <div className="dialog-actions">
          <button className="btn primary" data-testid="user-submit" disabled={!name.trim() || (passwordMode && !password) || busy}>
            {passwordMode ? (busy ? "Giriş yapılıyor…" : "Giriş yap") : "Devam"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function ProjectsPage() {
  const projects = useStudio((s) => s.projects);
  const loaded = useStudio((s) => s.projectsLoaded);
  const { loadProjects, openProject, notify } = useActions();
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  return (
    <div className="page" data-testid="projects-page">
      <div className="page-head">
        <div>
          <h1>Projeler</h1>
          <p>Gereksinim setinden test durumlarına ve gereksinim-test matrisine.</p>
        </div>
        <button className="btn primary" data-testid="import-open" onClick={() => setImporting(true)}>
          + Gereksinim seti yükle
        </button>
      </div>
      <div className="project-list">
        {projects.map((p) => (
          <button
            key={p.id}
            className="project-item"
            data-testid={`project-${p.id}`}
            onClick={() => openProject(p.id).catch((e: Error) => notify("error", `Proje açılamadı: ${e.message}`))}
          >
            <strong>{p.name}</strong>
            <small>{p.id}</small>
          </button>
        ))}
        {loaded && projects.length === 0 && (
          <div className="empty" data-testid="projects-empty">
            <strong>Henüz proje yok</strong>
            <span>Bir csv ya da xlsx dosyası yükleyerek başla.</span>
          </div>
        )}
      </div>
      {importing && <ImportDialog onClose={() => setImporting(false)} />}
    </div>
  );
}

const NONE = "";

function ImportDialog({ onClose }: { onClose: () => void }) {
  const { importProject } = useActions();
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [tables, setTables] = useState<SheetTables | null>(null);
  const [sheetIdx, setSheetIdx] = useState(0);
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [map, setMap] = useState({ text: "", id: "", language: "", source: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const table = tables?.sheets[sheetIdx]?.table;

  async function pick(f: File | undefined) {
    if (!f) return;
    setError("");
    try {
      const t = await readTables(f);
      setFile(f);
      setTables(t);
      setSheetIdx(0);
      const first = t.sheets[0]?.table;
      if (first) setMap(guessMapping(first.headers));
      if (!name) setName(f.name.replace(/\.[^.]+$/, ""));
    } catch {
      setError("Dosya okunamadı. csv ya da xlsx yükle.");
    }
  }

  function changeSheet(i: number) {
    setSheetIdx(i);
    const t = tables?.sheets[i]?.table;
    if (t) setMap(guessMapping(t.headers));
  }

  async function submit() {
    if (!file || !map.text) return;
    setBusy(true);
    setError("");
    const meta: ImportRequest = {
      name: name.trim(),
      key: key.trim(),
      mapping: {
        text: map.text,
        id: map.id || null,
        language: map.language || null,
        source: map.source || null,
      },
      sheet: tables && tables.sheets.length > 1 ? (tables.sheets[sheetIdx]?.name ?? null) : null,
    };
    try {
      await importProject(meta, file);
      onClose();
    } catch (e) {
      setError(`İçe alma başarısız: ${(e as Error).message}`);
      setBusy(false);
    }
  }

  const keyValid = /^[A-Za-z0-9_-]+$/.test(key.trim());
  const ready = !!file && !!map.text && !!name.trim() && keyValid && !busy;
  const mappedCols = new Set(Object.values(map).filter(Boolean));
  const colSelect = (field: keyof typeof map, label: string, optional: boolean) => (
    <div className="field">
      <label htmlFor={`map-${field}`}>{label}</label>
      <select id={`map-${field}`} data-testid={`map-${field}`} className="select" value={map[field]} onChange={(e) => setMap({ ...map, [field]: e.target.value })}>
        {optional && <option value={NONE}>(yok)</option>}
        {table?.headers.map((h) => (
          <option key={h} value={h}>
            {h}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Gereksinim seti yükle">
      <div className="dialog wide" data-testid="import-dialog">
        <h2>Gereksinim seti yükle</h2>
        <p className="sub">csv ya da xlsx dosyası seç, hangi kolonun ne olduğunu belirle.</p>
        <div className="dropzone" onClick={() => fileInput.current?.click()} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void pick(e.dataTransfer.files[0]); }}>
          <strong>{file ? file.name : "Dosyayı sürükle ya da seçmek için tıkla"}</strong>
          <span>{file && table ? `${table.rows.length} satır, ${table.headers.length} kolon` : "csv, xlsx"}</span>
          <input ref={fileInput} data-testid="import-file" type="file" accept=".csv,.xlsx" hidden onChange={(e) => void pick(e.target.files?.[0])} />
        </div>
        {table && (
          <>
            {tables && tables.sheets.length > 1 && (
              <div className="field">
                <label htmlFor="sheet">Sayfa</label>
                <select id="sheet" className="select" value={sheetIdx} onChange={(e) => changeSheet(Number(e.target.value))}>
                  {tables.sheets.map((s, i) => (
                    <option key={s.name} value={i}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="label" style={{ marginBottom: 6 }}>
              Önizleme (ilk 5 satır)
            </div>
            <div className="preview" data-testid="import-preview">
              <table>
                <thead>
                  <tr>
                    {table.headers.map((h) => (
                      <th key={h} className={mappedCols.has(h) ? "mapped" : ""}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.slice(0, 5).map((r, i) => (
                    <tr key={i}>
                      {r.map((c, j) => (
                        <td key={j}>{c}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row">
              {colSelect("text", "Gereksinim metni (zorunlu)", false)}
              {colSelect("id", "Kimlik", true)}
              {colSelect("language", "Dil", true)}
              {colSelect("source", "Kaynak", true)}
            </div>
            <div className="row">
              <div className="field">
                <label htmlFor="pname">Proje adı</label>
                <input id="pname" data-testid="import-name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="pkey">Anahtar (ör. KDH)</label>
                <input id="pkey" data-testid="import-key" className="input" value={key} onChange={(e) => setKey(e.target.value)} />
                {key && !keyValid && <span className="error-text">Yalnızca harf, rakam, tire ve alt çizgi.</span>}
              </div>
            </div>
          </>
        )}
        {error && <div className="error-text" data-testid="import-error">{error}</div>}
        <div className="dialog-actions">
          <button className="btn" onClick={onClose}>
            Vazgeç
          </button>
          <button className="btn primary" data-testid="import-submit" disabled={!ready} onClick={() => void submit()}>
            {busy ? "Yükleniyor…" : "İçe al ve başlat"}
          </button>
        </div>
      </div>
    </div>
  );
}
