import { requirements, testCaseContent } from "../api/selectors";
import { useActions, useStudio, useView } from "../context";

/** Pinned item went stale: keep mine, or take a new one (unpin + regenerate). The contract has no
 *  proposed new content, so the screen shows the pinned content next to the current inputs. */
export function DiffDialog() {
  const state = useView();
  const diffFor = useStudio((s) => s.diffFor);
  const { openDiff, send } = useActions();
  const node = state && diffFor ? state.nodes[diffFor] : undefined;
  if (!state || !diffFor || !node) return null;
  const tc = testCaseContent(node);
  const reqs = requirements(state);
  const inputs = tc ? tc.covers.map((id) => [...reqs.values()].find((r) => r.id === id)).filter((r) => r !== undefined) : [];

  async function takeNew() {
    if (!node) return;
    const r = await send({ type: "unpin", node: node.ref });
    if (r?.accepted) await send({ type: "regenerate", node: node.ref });
    openDiff(null);
  }

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Fark ekranı">
      <div className="dialog wide" data-testid="diff-dialog">
        <h2>Sabit öğenin girdileri değişti</h2>
        <p className="sub">Benim sürümümü koruyabilir ya da yenisini ürettirebilirsin. Yenisini almak sabitlemeyi çözer.</p>
        <div className="diff">
          <div>
            <h4>Benim sürümüm (v{node.version})</h4>
            {tc ? (
              <>
                <div className="box">
                  <strong>{tc.id}</strong> {tc.title}
                </div>
                {tc.steps.map((s) => (
                  <div className="box" key={s.no}>
                    <div className="label">Adım {s.no}</div>
                    <div>{s.action}</div>
                    <div style={{ color: "var(--text-2)", marginTop: 4 }}>→ {s.expected}</div>
                  </div>
                ))}
              </>
            ) : (
              <div className="box">{JSON.stringify(node.content)}</div>
            )}
          </div>
          <div>
            <h4>Güncel girdiler</h4>
            {inputs.length === 0 && <div className="box">Girdi bilgisi yok.</div>}
            {inputs.map((r) => (
              <div className="box" key={r.id}>
                <strong>{r.id}</strong>
                <div>{r.text}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="dialog-actions">
          <button className="btn" onClick={() => openDiff(null)}>
            Kapat
          </button>
          <button
            className="btn"
            data-testid="diff-keep"
            onClick={async () => {
              await send({ type: "keep_mine", node: node.ref });
              openDiff(null);
            }}
          >
            Benimkini koru
          </button>
          <button className="btn primary" data-testid="diff-new" onClick={() => void takeNew()}>
            Yenisini al
          </button>
        </div>
      </div>
    </div>
  );
}
