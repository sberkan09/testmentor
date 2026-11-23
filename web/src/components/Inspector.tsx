import { useEffect, useState } from "react";
import { clusters, projectMethods, requirements, testCaseContent } from "../api/selectors";
import type { ProjectState } from "../api/state";
import { useActions, useStudio, useView } from "../context";
import { makeRef, refKey, type NodeView, type TestCaseContent } from "../types";
import { PinIcon, StatusPill } from "./ui";

function useEditLock(state: ProjectState, node: NodeView | undefined, dirty: boolean) {
  const user = useStudio((s) => s.user);
  const { lock } = useActions();
  const key = node ? refKey(node.ref) : "";
  const holder = state.locks[key];
  const lockedByOther = !!holder && holder !== user;
  const ref = node?.ref;
  useEffect(() => {
    if (!dirty || !ref) return;
    void lock(ref);
    const t = setInterval(() => void lock(ref), 20000);
    return () => clearInterval(t);
  }, [dirty, ref, lock]);
  return { lockedByOther, holder };
}

function Banners({ node, holder, lockedByOther }: { node: NodeView; holder?: string; lockedByOther: boolean }) {
  const { openDiff, send } = useActions();
  return (
    <>
      {lockedByOther && (
        <div className="banner lock" data-testid="lock-banner">
          {holder} bu öğeyi düzenliyor. Bitirene kadar değiştiremezsin.
        </div>
      )}
      {node.status === "failed" && (
        <div className="banner failed" data-testid="failed-banner">
          Üretim başarısız oldu.
          <button className="btn small danger" data-testid="retry" onClick={() => void send({ type: "regenerate", node: node.ref })}>
            Yeniden dene
          </button>
        </div>
      )}
      {node.pinned_warning && (
        <div className="banner stale" data-testid="pinned-warning">
          Sabitlediğin öğenin girdileri değişti; içerik güncel olmayabilir.
          <button className="btn small" data-testid="open-diff" onClick={() => openDiff(refKey(node.ref))}>
            Farkı göster
          </button>
        </div>
      )}
    </>
  );
}

function History({ state, node }: { state: ProjectState; node: NodeView }) {
  const items = [...(state.history[refKey(node.ref)] ?? [])].reverse();
  if (items.length === 0) return null;
  return (
    <>
      <div className="section-title">Sürüm geçmişi (bu oturum)</div>
      <ul className="history" data-testid="history">
        {items.map((h) => (
          <li key={`${h.seq}-${h.version}`}>
            <strong>v{h.version}</strong>
            <span>{h.origin === "edited" ? "düzenlendi" : "üretildi"}</span>
            <span style={{ marginLeft: "auto" }}>{h.actor}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function PinButton({ node }: { node: NodeView }) {
  const { send } = useActions();
  return (
    <button
      className="btn"
      data-testid={node.pinned ? "unpin" : "pin"}
      disabled={node.content === null}
      onClick={() => void send({ type: node.pinned ? "unpin" : "pin", node: node.ref })}
    >
      <PinIcon /> {node.pinned ? "Sabitlemeyi çöz" : "Sabitle"}
    </button>
  );
}

function TestCaseEditor({ state, node }: { state: ProjectState; node: NodeView }) {
  const { send } = useActions();
  const server = testCaseContent(node);
  const [draft, setDraft] = useState<{ base: number; value: TestCaseContent } | null>(null);
  const dirty = draft !== null;
  const { lockedByOther, holder } = useEditLock(state, node, dirty);
  const streamed = state.progress[refKey(node.ref)];
  if (!server) {
    return (
      <div className="empty">
        <strong>{streamed ? "Üretiliyor" : "Test durumu henüz üretilmedi"}</strong>
        {streamed && <div className="streaming">{streamed}</div>}
      </div>
    );
  }
  const c = draft?.value ?? server;
  const disabled = lockedByOther || node.status === "running";
  const patch = (p: Partial<TestCaseContent>) => setDraft({ base: draft?.base ?? node.version, value: { ...c, ...p } });
  const setStep = (i: number, p: Partial<TestCaseContent["steps"][number]>) =>
    patch({ steps: c.steps.map((s, j) => (j === i ? { ...s, ...p } : s)) as TestCaseContent["steps"] });
  const remoteChanged = draft !== null && draft.base !== node.version;

  async function save() {
    if (!draft) return;
    const steps = draft.value.steps.map((s, i) => ({ ...s, no: i + 1 })) as TestCaseContent["steps"];
    const res = await send({ type: "edit_test_case", case: node.ref.key, content: { ...draft.value, steps } });
    if (res?.accepted) setDraft(null);
  }

  return (
    <div data-testid="inspector-test-case">
      <div className="insp-head">
        <span className="kind">Test durumu</span>
        <StatusPill node={node} />
        {node.pinned && (
          <span className="pill pinned" data-testid="pinned-pill">
            <PinIcon size={11} /> Sabit
          </span>
        )}
        <h2>{c.id}</h2>
      </div>
      <div className="meta">
        v{node.version} · {node.origin === "edited" ? "düzenlendi" : "üretildi"} {node.produced_by?.["model"] ? `· ${String(node.produced_by["model"])}` : ""}
      </div>
      <Banners node={node} holder={holder} lockedByOther={lockedByOther} />
      {remoteChanged && (
        <div className="banner stale">Sen düzenlerken sunucudaki sürüm değişti (v{node.version}). Kaydedersen çakışma uyarısı alabilirsin.</div>
      )}
      {streamed && <div className="streaming" data-testid="inspector-stream">{streamed}</div>}
      <div className="field">
        <label htmlFor="tc-title">Başlık</label>
        <input id="tc-title" data-testid="tc-title" className="input" disabled={disabled} value={c.title} onChange={(e) => patch({ title: e.target.value })} />
      </div>
      <div className="row">
        <div className="field">
          <label htmlFor="tc-type">Tür</label>
          <input id="tc-type" className="input" disabled={disabled} value={c.type} onChange={(e) => patch({ type: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="tc-priority">Öncelik</label>
          <input id="tc-priority" className="input" disabled={disabled} value={c.priority} onChange={(e) => patch({ priority: e.target.value })} />
        </div>
      </div>
      <div className="field">
        <span className="label">Kapsadığı gereksinimler</span>
        <div className="chips">
          {c.covers.map((r) => (
            <span key={r} className="link-chip" style={{ cursor: "default" }}>
              {r}
            </span>
          ))}
        </div>
      </div>
      <div className="field">
        <label htmlFor="tc-pre">Ön koşul</label>
        <textarea id="tc-pre" data-testid="tc-preconditions" className="textarea" disabled={disabled} rows={2} value={c.preconditions} onChange={(e) => patch({ preconditions: e.target.value })} />
      </div>
      <div className="field">
        <label htmlFor="tc-in">Test girdisi</label>
        <textarea id="tc-in" className="textarea" disabled={disabled} rows={2} value={c.test_inputs} onChange={(e) => patch({ test_inputs: e.target.value })} />
      </div>
      <div className="field">
        <label htmlFor="tc-as">Varsayım</label>
        <textarea id="tc-as" className="textarea" disabled={disabled} rows={2} value={c.assumptions} onChange={(e) => patch({ assumptions: e.target.value })} />
      </div>
      <div className="section-title">Adımlar</div>
      {c.steps.map((s, i) => (
        <div className="step-card" key={i} data-testid={`step-${i + 1}`}>
          <div className="step-head">
            <span className="step-no">Adım {i + 1}</span>
            {c.steps.length > 1 && !disabled && (
              <button className="icon-btn" aria-label={`Adım ${i + 1} sil`} onClick={() => patch({ steps: c.steps.filter((_, j) => j !== i) as TestCaseContent["steps"] })}>
                ×
              </button>
            )}
          </div>
          <div className="field">
            <label htmlFor={`st-a-${i}`}>İşlem</label>
            <textarea id={`st-a-${i}`} data-testid={`step-${i + 1}-action`} className="textarea" rows={2} disabled={disabled} value={s.action} onChange={(e) => setStep(i, { action: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor={`st-e-${i}`}>Beklenen sonuç</label>
            <textarea id={`st-e-${i}`} data-testid={`step-${i + 1}-expected`} className="textarea" rows={2} disabled={disabled} value={s.expected} onChange={(e) => setStep(i, { expected: e.target.value })} />
          </div>
        </div>
      ))}
      {!disabled && (
        <button
          className="btn small"
          data-testid="add-step"
          onClick={() => patch({ steps: [...c.steps, { no: c.steps.length + 1, action: "", expected: "" }] as TestCaseContent["steps"] })}
        >
          + Adım ekle
        </button>
      )}
      <div className="actions">
        <button
          className="btn primary"
          data-testid="save"
          disabled={!dirty || disabled || c.steps.some((s) => !s.action.trim() || !s.expected.trim()) || !c.title.trim()}
          onClick={() => void save()}
        >
          Kaydet
        </button>
        {dirty && (
          <button className="btn" onClick={() => setDraft(null)}>
            Değişiklikleri at
          </button>
        )}
        <PinButton node={node} />
      </div>
      <History state={state} node={node} />
    </div>
  );
}

function RequirementEditor({ state, node }: { state: ProjectState; node: NodeView }) {
  const { send, select } = useActions();
  const req = requirements(state).get(node.ref.key);
  const methodNode = state.nodes[`method:${node.ref.key}`];
  const methodNames = projectMethods(state).map((m) => m.name);
  const current = (methodNode?.content?.["methods"] as string[] | undefined) ?? [];
  const [text, setText] = useState<string | null>(null);
  const [methods, setMethods] = useState<string[] | null>(null);
  const { lockedByOther, holder } = useEditLock(state, node, text !== null);
  const owner = clusters(state).find((c) => c.members.some((m) => m.node.ref.key === node.ref.key));
  const list = clusters(state);
  if (!req) return null;
  const cases = Object.values(state.nodes).filter((n) => n.ref.kind === "test_case" && testCaseContent(n)?.covers.includes(req.id));
  const shownMethods = methods ?? current;
  const options = Array.from(new Set([...methodNames, ...current]));
  return (
    <div data-testid="inspector-requirement">
      <div className="insp-head">
        <span className="kind">Gereksinim</span>
        <StatusPill node={node} />
        {node.pinned && <PinIcon />}
        <h2>{req.id}</h2>
      </div>
      <div className="meta">
        v{node.version} · dil: {req.language || "?"}
      </div>
      <Banners node={node} holder={holder} lockedByOther={lockedByOther} />
      <div className="field">
        <label htmlFor="rq-text">Metin</label>
        <textarea id="rq-text" data-testid="req-text" className="textarea" rows={5} disabled={lockedByOther} value={text ?? req.text} onChange={(e) => setText(e.target.value)} />
        <div>
          <button
            className="btn small primary"
            data-testid="req-save"
            disabled={text === null || !text.trim() || text === req.text || lockedByOther}
            onClick={async () => {
              const res = await send({ type: "edit_requirement", requirement: node.ref.key, text: (text ?? "").trim() });
              if (res?.accepted) setText(null);
            }}
          >
            Metni kaydet
          </button>
        </div>
      </div>
      <div className="field">
        <label htmlFor="rq-cluster">Öbek</label>
        <select
          id="rq-cluster"
          data-testid="req-cluster"
          className="select"
          value={owner?.key ?? ""}
          onChange={(e) => void send({ type: "move_requirement", requirement: node.ref.key, to_cluster: e.target.value })}
        >
          {list.map((c) => (
            <option key={c.key} value={c.key}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      {methodNode && (
        <div className="field">
          <span className="label">Doğrulama yöntemi</span>
          <div className="check-list">
            {options.map((m) => (
              <label className="check" key={m}>
                <input
                  type="checkbox"
                  checked={shownMethods.includes(m)}
                  onChange={(e) => setMethods(e.target.checked ? [...shownMethods, m] : shownMethods.filter((x) => x !== m))}
                />
                {m}
              </label>
            ))}
          </div>
          {methods !== null && (
            <div>
              <button
                className="btn small primary"
                disabled={methods.length === 0}
                onClick={async () => {
                  const res = await send({ type: "edit_method", requirement: node.ref.key, methods: methods as [string, ...string[]] });
                  if (res?.accepted) setMethods(null);
                }}
              >
                Yöntemi kaydet
              </button>
            </div>
          )}
          {methodNode.content?.["rationale"] ? <p className="meta">{String(methodNode.content["rationale"])}</p> : null}
        </div>
      )}
      <div className="section-title">Kapsayan test durumları</div>
      {cases.length === 0 ? (
        <span className="pill warn" data-testid="req-uncovered">
          Kapsanmamış
        </span>
      ) : (
        cases.map((n) => (
          <button key={n.ref.key} className="case-row" onClick={() => select({ kind: "test_case", key: n.ref.key })}>
            <span className="cid">{testCaseContent(n)?.id}</span>
            <span className="ctitle">{testCaseContent(n)?.title}</span>
          </button>
        ))
      )}
      <History state={state} node={node} />
    </div>
  );
}

/** Passages the retrieval node of the cluster found in the knowledge base (paket 10). An id is
 *  `<document>#<chunk>@<digest>`; the document and chunk number are shown. */
function Passages({ state, clusterKey }: { state: ProjectState; clusterKey: string }) {
  const node = state.nodes[`retrieval:${clusterKey}`];
  if (!node) return null;
  const ids = (node.content?.["passage_ids"] as string[] | undefined) ?? [];
  return (
    <>
      <div className="section-title">Bilgi havuzundan parçalar ({ids.length})</div>
      {ids.length === 0 ? (
        <span className="meta" data-testid="passages-empty">
          {node.status === "fresh" ? "Parça yok; Belgeler sekmesinden belge yükleyebilirsin." : "Aranıyor…"}
        </span>
      ) : (
        <div className="chips" data-testid="passages">
          {ids.map((id) => (
            <span key={id} className="link-chip" style={{ cursor: "default" }} title={id} data-testid="passage-id">
              {id.split("@")[0]}
            </span>
          ))}
        </div>
      )}
    </>
  );
}

function ClusterEditor({ state, clusterKey }: { state: ProjectState; clusterKey: string }) {
  const { send, select } = useActions();
  const c = clusters(state).find((x) => x.key === clusterKey);
  const [name, setName] = useState<string | null>(null);
  const label = c?.labelNode;
  const { lockedByOther, holder } = useEditLock(state, label, name !== null);
  if (!c) return null;
  const streamed = state.progress[`cluster_label:${clusterKey}`];
  return (
    <div data-testid="inspector-cluster">
      <div className="insp-head">
        <span className="kind">Öbek</span>
        <StatusPill node={label} />
        <h2>{c.name}</h2>
      </div>
      <div className="meta">{c.members.length} gereksinim</div>
      {label && <Banners node={label} holder={holder} lockedByOther={lockedByOther} />}
      {streamed && <div className="streaming">{streamed}</div>}
      <div className="field">
        <label htmlFor="cl-name">Ad</label>
        <input id="cl-name" data-testid="cluster-name-input" className="input" disabled={lockedByOther} value={name ?? c.name} onChange={(e) => setName(e.target.value)} />
        <div>
          <button
            className="btn small primary"
            disabled={name === null || !name.trim() || name === c.name || lockedByOther}
            onClick={async () => {
              const res = await send({ type: "rename_cluster", cluster: clusterKey, name: (name ?? "").trim() });
              if (res?.accepted) setName(null);
            }}
          >
            Adı kaydet
          </button>
        </div>
      </div>
      {c.rationale && (
        <div className="field">
          <span className="label">Gerekçe</span>
          <p>{c.rationale}</p>
        </div>
      )}
      <Passages state={state} clusterKey={clusterKey} />
      <div className="section-title">Test durumları ({c.caseKeys.length})</div>
      {c.caseKeys.map((k) => {
        const n = state.nodes[`test_case:${k}`];
        const tc = testCaseContent(n);
        return (
          <button key={k} className="case-row" onClick={() => select({ kind: "test_case", key: k })}>
            <span className="cid">{tc?.id ?? k}</span>
            <span className="ctitle">{tc?.title ?? "Üretiliyor…"}</span>
          </button>
        );
      })}
      {label && <History state={state} node={label} />}
    </div>
  );
}

export function Inspector() {
  const state = useView();
  const selection = useStudio((s) => s.selection);
  if (!state || !selection) {
    return (
      <div className="empty" data-testid="inspector-empty">
        <strong>Denetçi</strong>
        <span>Bir gereksinim, öbek ya da test durumu seç.</span>
      </div>
    );
  }
  const refOf = makeRef(selection.kind, selection.key);
  const node = state.nodes[refKey(refOf)];
  let body: React.ReactNode;
  if (selection.kind === "cluster") body = <ClusterEditor key={selection.key} state={state} clusterKey={selection.key} />;
  else if (!node) body = <div className="empty"><strong>Öğe artık yok</strong></div>;
  else if (selection.kind === "requirement") body = <RequirementEditor key={selection.key} state={state} node={node} />;
  else body = <TestCaseEditor key={selection.key} state={state} node={node} />;
  return <div className="inspector-inner">{body}</div>;
}
