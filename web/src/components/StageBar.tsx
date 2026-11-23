import { runningText, STAGE_LABELS, stageViews } from "../api/selectors";
import { useActions, useView } from "../context";

const HIDDEN = new Set(["requirement", "project_card", "kb_index", "cluster", "embedding", "clustering", "retrieval"]);

export function StageBar() {
  const state = useView();
  const { send } = useActions();
  if (!state) return null;
  const stages = stageViews(state).filter((s) => !HIDDEN.has(s.stage) || s.running + s.stale + s.failed > 0 || s.waiting_approval);
  const jobs = Object.values(state.jobs);
  const running = jobs.filter((j) => j.state === "running").length;
  const queued = jobs.filter((j) => j.state === "queued").length;
  const waiting = jobs.filter((j) => j.state === "waiting_approval").length;
  const total = stages.reduce((n, s) => n + s.fresh + s.stale + s.running + s.failed, 0);
  const done = stages.reduce((n, s) => n + s.fresh, 0);
  const stream = runningText(state);
  const streamLabel = stream ? stream.key.split(":")[0] : "";

  return (
    <div className="stagebar" data-testid="stagebar">
      <div className="stagebar-left">
        <button className="btn small" data-testid="undo" onClick={() => void send({ type: "undo" })} title="Ctrl+Z">
          ↶ Geri al
        </button>
      </div>
      <div className="stages" role="list">
        {stages.map((s) => (
          <div key={s.stage} role="listitem" className={`stage${s.waiting_approval ? " waiting" : ""}`} data-testid={`stage-${s.stage}`}>
            <div className="stage-head">
              <span>{STAGE_LABELS[s.stage] ?? s.stage}</span>
            </div>
            <div className="stage-counts">
              <span className="pill fresh" title="Taze">{s.fresh}</span>
              {s.running > 0 && (
                <span className="pill running" title="Üretiliyor" data-testid={`stage-running-${s.stage}`}>
                  <span className="dot" />
                  {s.running}
                </span>
              )}
              {s.stale > 0 && <span className="pill stale" title="Bayat">{s.stale}</span>}
              {s.failed > 0 && <span className="pill failed" title="Hata">{s.failed}</span>}
            </div>
            <div className="mode-toggle" role="group" aria-label="Aşama modu">
                <button aria-pressed={s.mode === "auto"} data-testid={`mode-auto-${s.stage}`} onClick={() => void send({ type: "set_stage_mode", stage: s.stage, mode: "auto" })}>
                  Otomatik
                </button>
                <button aria-pressed={s.mode === "approval"} data-testid={`mode-approval-${s.stage}`} onClick={() => void send({ type: "set_stage_mode", stage: s.stage, mode: "approval" })}>
                  Onaylı
                </button>
              </div>
            {s.waiting_approval && (
              <button className="btn small primary" data-testid={`approve-${s.stage}`} onClick={() => void send({ type: "approve_stage", stage: s.stage })}>
                Onayla
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="queue" data-testid="queue">
        <div>
          {running > 0 || queued > 0 || waiting > 0 ? (
            <>
              <strong>{running}</strong> çalışıyor · <strong>{queued}</strong> sırada
              {waiting > 0 && <> · <strong>{waiting}</strong> onay bekliyor</>}
            </>
          ) : (
            "Kuyruk boş"
          )}
        </div>
        <div className="progress-bar" aria-label="Genel ilerleme">
          <div style={{ width: total ? `${Math.round((done / total) * 100)}%` : "0%" }} />
        </div>
        {stream && (
          <div className="streaming" data-testid="stagebar-stream" title={streamLabel}>
            {stream.text.slice(-140)}
          </div>
        )}
      </div>
    </div>
  );
}
