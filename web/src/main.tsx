import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { createRestApi } from "./api/client";
import { createStudioStore } from "./api/store";
import { StudioProvider } from "./context";
import "./styles.css";

// The REST client reads the user name lazily: it is asked on first launch.
let userName = "";
const api = createRestApi(() => userName || "anonim");
const store = createStudioStore({ api, warningRefreshMs: 800 });
userName = store.getState().user ?? "";
store.subscribe((s) => {
  userName = s.user ?? "";
});

const root = document.getElementById("root");
if (!root) throw new Error("#root yok");
createRoot(root).render(
  <StrictMode>
    <StudioProvider store={store} api={api}>
      <App />
    </StudioProvider>
  </StrictMode>,
);
