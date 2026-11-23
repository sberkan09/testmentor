import { useMemo, useState } from "react";
import { matrixRows, projectMethods } from "../api/selectors";
import { useActions, useApi, useView } from "../context";

const WARNING_TEXT: Record<string, string> = {
  test_without_case: "Yöntemi Test, ama test durumu yok",
  case_without_test_method: "Yöntemi Test değil, ama test yazılmış",
};

export function MatrixView() {
  const state = useView();
  const api = useApi();
  const { select } = useActions();
  const [cluster, setCluster] = useState("");
  const [method, setMethod] = useState("");
  const [warning, setWarning] = useState("");
  const [coverage, setCoverage] = useState("");
  const rows = useMemo(() => (state ? matrixRows(state) : []), [state]);
  if (!state) return null;

  const clusterOptions = Array.from(new Map(rows.filter((r) => r.cluster).map((r) => [r.cluster, r.cluster_name])));
  const methodOptions = Array.from(new Set([...projectMethods(state).map((m) => m.name), ...rows.flatMap((r) => r.methods)]));
  const shown = rows.filter(
    (r) =>
      (!cluster || r.cluster === cluster) &&
      (!method || r.methods.includes(method)) &&
      (!warning || (warning === "any" ? r.warning !== "" : r.warning === warning)) &&
      (!coverage || (coverage === "covered" ? r.covered : !r.covered)),
  );
  const covered = rows.filter((r) => r.covered).length;
  const warnCount = rows.filter((r) => r.warning).length;
  const pct = rows.length ? Math.round((covered / rows.length) * 100) : 0;

  return (
    <>
      <div className="canvas-toolbar" data-testid="matrix-toolbar">
        <div className="summary">
          <span>
            <strong data-testid="matrix-coverage">%{pct}</strong> kapsama
          </span>
          <span>
            <strong data-testid="matrix-covered">{covered}</strong> / {rows.length} gereksinim kapsanmış
          </span>
          <span>
            <strong data-testid="matrix-warnings">{warnCount}</strong> uyarı
          </span>
        </div>
        <div className="spacer" />
        <a className="btn primary" data-testid="matrix-download" href={api.matrixUrl(state.projectId)} download={`${state.projectId}-matris.xlsx`}>
          ⬇ xlsx indir
        </a>
      </div>
      <div className="canvas-toolbar filters" style={{ paddingTop: 0 }}>
        <select className="select" aria-label="Öbek" data-testid="filter-cluster" value={cluster} onChange={(e) => setCluster(e.target.value)}>
          <option value="">Tüm öbekler</option>
          {clusterOptions.map(([k, n]) => (
            <option key={k} value={k}>
              {n}
            </option>
          ))}
        </select>
        <select className="select" aria-label="Yöntem" data-testid="filter-method" value={method} onChange={(e) => setMethod(e.target.value)}>
          <option value="">Tüm yöntemler</option>
          {methodOptions.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select className="select" aria-label="Uyarı" data-testid="filter-warning" value={warning} onChange={(e) => setWarning(e.target.value)}>
          <option value="">Uyarı: hepsi</option>
          <option value="any">Uyarısı olanlar</option>
          <option value="test_without_case">{WARNING_TEXT.test_without_case}</option>
          <option value="case_without_test_method">{WARNING_TEXT.case_without_test_method}</option>
        </select>
        <select className="select" aria-label="Kapsama" data-testid="filter-coverage" value={coverage} onChange={(e) => setCoverage(e.target.value)}>
          <option value="">Kapsama: hepsi</option>
          <option value="covered">Kapsanmış</option>
          <option value="uncovered">Kapsanmamış</option>
        </select>
        <span className="meta" style={{ margin: 0 }}>
          {shown.length} satır
        </span>
      </div>
      <div className="canvas-body">
        {rows.length === 0 ? (
          <div className="empty">
            <strong>Matris boş</strong>
            <span>Gereksinimler yüklenince satırlar burada görünür.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="matrix" data-testid="matrix-table">
              <thead>
                <tr>
                  <th>Gereksinim</th>
                  <th>Öbek</th>
                  <th>Yöntem</th>
                  <th>Test durumları</th>
                  <th>Kapsama</th>
                  <th>Uyarı</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.requirement_id} className={r.covered ? "" : "uncovered"} data-testid={`row-${r.requirement_id}`}>
                    <td>
                      <button className="link-chip" onClick={() => select({ kind: "requirement", key: r.requirement_id })}>
                        {r.requirement_id}
                      </button>
                      <div className="rtext">{r.text}</div>
                    </td>
                    <td>{r.cluster_name}</td>
                    <td>
                      {r.methods.map((m) => (
                        <span key={m} className="pill" style={{ marginRight: 4 }}>
                          {m}
                        </span>
                      ))}
                    </td>
                    <td>
                      {r.test_case_keys.map((k) => (
                        <button key={k} className="link-chip" data-testid={`matrix-case-${k}`} onClick={() => select({ kind: "test_case", key: k })}>
                          {k.split(":").slice(1).join(":") || k}
                        </button>
                      ))}
                    </td>
                    <td>
                      {r.covered ? (
                        <span className="pill fresh" data-testid={`covered-${r.requirement_id}`}>
                          Kapsanmış
                        </span>
                      ) : (
                        <span className="pill warn" data-testid={`uncovered-${r.requirement_id}`}>
                          Kapsanmamış
                        </span>
                      )}
                    </td>
                    <td>{r.warning && <span className="pill warn">{WARNING_TEXT[r.warning]}</span>}</td>
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
