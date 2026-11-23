import type { NodeView } from "../types";
import { useActions, useStudio } from "../context";

export function PinIcon({ size = 14 }: { size?: number }) {
  return (
    <svg className="pin-icon" width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-label="Sabit" role="img">
      <path d="M16 3a1 1 0 0 1 .7 1.7L15.4 6l1.6 5 2 1.5V14h-6v6l-1 1-1-1v-6H5v-1.5L7 11l1.6-5L7.3 4.7A1 1 0 0 1 8 3h8z" />
    </svg>
  );
}

export const STATUS_LABEL: Record<string, string> = {
  fresh: "Taze",
  stale: "Bayat",
  running: "Üretiliyor",
  failed: "Hata",
};

export function StatusPill({ node }: { node: NodeView | undefined }) {
  if (!node) return null;
  return (
    <span className={`pill ${node.status}`} data-testid={`status-${node.status}`}>
      <span className="dot" />
      {node.waiting && node.status === "fresh" ? "Bekliyor" : STATUS_LABEL[node.status]}
    </span>
  );
}

export function Toasts() {
  const notices = useStudio((s) => s.notices);
  const { dismiss } = useActions();
  return (
    <div className="toasts" role="status" aria-live="polite">
      {notices.map((n) => (
        <div key={n.id} className={`toast ${n.kind}`} data-testid="toast">
          <span>{n.text}</span>
          <button className="icon-btn" aria-label="Kapat" onClick={() => dismiss(n.id)}>
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

export function initials(name: string): string {
  return name.trim().slice(0, 2).toLocaleUpperCase("tr");
}
