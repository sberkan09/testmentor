import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useStore } from "zustand";
import type { StudioApi } from "./api/client";
import type { ProjectState } from "./api/state";
import { applyPending } from "./api/optimistic";
import type { StudioState, StudioStore } from "./api/store";

interface Ctx {
  store: StudioStore;
  api: StudioApi;
}

const StudioContext = createContext<Ctx | null>(null);

export function StudioProvider({ store, api, children }: { store: StudioStore; api: StudioApi; children: ReactNode }) {
  const value = useMemo(() => ({ store, api }), [store, api]);
  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
}

function useCtx(): Ctx {
  const c = useContext(StudioContext);
  if (!c) throw new Error("StudioProvider eksik");
  return c;
}

export function useStudio<T>(selector: (s: StudioState) => T): T {
  return useStore(useCtx().store, selector);
}

export function useActions(): StudioState {
  return useCtx().store.getState();
}

export function useApi(): StudioApi {
  return useCtx().api;
}

/** Server state plus the unconfirmed local predictions. */
export function useView(): ProjectState | null {
  const server = useStudio((s) => s.server);
  const pending = useStudio((s) => s.pending);
  return useMemo(() => (server ? applyPending(server, pending) : null), [server, pending]);
}
