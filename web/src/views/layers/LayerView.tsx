import { Component, memo, useCallback, useMemo, useRef, type ReactNode } from "react";
import { Canvas } from "@react-three/fiber";
import { LinearSRGBColorSpace } from "three";
import { useActions, useView } from "../../context";
import { buildLayout } from "./layout";
import { COLORS } from "./objects";
import { LayerScene, type LayerPick, type SceneHandle } from "./LayerScene";
import "./layers.css";

/** 3D layer view: clusters, test cases and the matrix as three stacked planes with the
 *  traceability threads between them. Navigation and selection only, no editing. Loaded lazily
 *  (its own chunk with three.js); the 2D views do not depend on it. */

class GlBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed) {
      return (
        <div className="empty" data-testid="layers-unsupported">
          <strong>3B görünüm açılamadı</strong>
          <span>Tarayıcı WebGL desteklemiyor ya da kapalı. Öbek ve matris görünümleri kullanılabilir.</span>
        </div>
      );
    }
    return this.props.children;
  }
}

/** Scrolls the 2D element into view once the new view has rendered it. */
function reveal(testId: string) {
  let tries = 0;
  const tick = () => {
    const el = document.querySelector(`[data-testid="${CSS.escape(testId)}"]`);
    if (el) el.scrollIntoView({ block: "center" });
    else if (tries++ < 30) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// Stable props: a new object on every render would make the canvas reconfigure its camera.
const CAMERA = { fov: 45, near: 0.5, far: 2000, position: [0, 60, 90] as [number, number, number] };
const GL = { antialias: false, alpha: false, powerPreference: "high-performance" as const };

function LayerView() {
  const state = useView();
  const { select, setView } = useActions();
  // Rebuild only when nodes or matrix warnings change (not on streamed text or job events).
  const nodes = state?.nodes;
  const warnings = state?.warnings;
  const layout = useMemo(() => (nodes && warnings ? buildLayout({ nodes, warnings }) : null), [nodes, warnings]);
  const labelsRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<SceneHandle | null>(null);

  const open2D = useCallback(
    (p: LayerPick) => {
      if (p.kind === "matrix") {
        select({ kind: "requirement", key: p.key });
        setView("matrix");
        reveal(`row-${p.id}`);
        return;
      }
      if (p.kind === "cluster") {
        if (p.key) select({ kind: "cluster", key: p.key });
      } else {
        select({ kind: p.kind, key: p.key });
      }
      setView("clusters");
      if (p.cluster) reveal(`cluster-${p.cluster}`);
    },
    [select, setView],
  );

  if (!state || !layout) return null;
  return (
    <div className="layers" data-testid="layers-view">
      <div className="canvas-toolbar">
        <div className="summary">
          <span>
            <strong>{layout.reqs.length}</strong> gereksinim
          </span>
          <span>
            <strong>{layout.cases.length}</strong> test durumu
          </span>
          <span>
            <strong data-testid="layers-uncovered">{layout.uncovered}</strong> kapsanmamış
          </span>
        </div>
        <div className="layer-legend" aria-label="Gösterim">
          <span>
            <i style={{ background: COLORS.requirement }} /> gereksinim
          </span>
          <span>
            <i className="ring" style={{ borderColor: COLORS.uncovered }} /> kapsanmamış
          </span>
          <span>
            <i style={{ background: COLORS.testCase }} /> test durumu
          </span>
          <span>
            <i style={{ background: COLORS.matrixCovered }} /> matris satırı
          </span>
          <span>
            <i className="line" style={{ background: COLORS.thread }} /> izlenebilirlik
          </span>
        </div>
        <div className="spacer" />
        <button className="btn small" data-testid="layers-reset" onClick={() => handleRef.current?.reset()}>
          Görünümü sıfırla
        </button>
      </div>
      <div className="layers-stage" data-testid="layers-stage">
        <GlBoundary>
          <Canvas
            frameloop="demand"
            dpr={1}
            flat
            legacy
            onCreated={({ gl }) => {
              // Colors are authored in sRGB and written as is: no per-fragment conversion.
              gl.outputColorSpace = LinearSRGBColorSpace;
            }}
            gl={GL}
            camera={CAMERA}
            aria-label="3B katman görünümü"
          >
            <color attach="background" args={[COLORS.background]} />
            <LayerScene layout={layout} labelsRef={labelsRef} handleRef={handleRef} onPick={open2D} />
          </Canvas>
        </GlBoundary>
        <div className="layer-labels" ref={labelsRef} aria-hidden="true" />
        <div className="layer-hint">Sürükle: döndür · Tekerlek: yakınlaş · Sağ tık: kaydır · Tıkla: 2B görünümde aç</div>
      </div>
    </div>
  );
}

export default memo(LayerView);
