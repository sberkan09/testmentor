import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { createRestApi } from "./api/client";
import { createStudioStore } from "./api/store";
import { StudioProvider } from "./context";
import "./styles.css";

// The REST client reads the user name and the login token lazily: they come from the store.
let userName = "";
let token: string | null = null;
let onUnauthorized = () => undefined as void;
const api = createRestApi(() => userName || "anonim", undefined, { getToken: () => token, onUnauthorized: () => onUnauthorized() });
const store = createStudioStore({ api, warningRefreshMs: 800 });
userName = store.getState().user ?? "";
token = store.getState().token;
store.subscribe((s) => {
  userName = s.user ?? "";
  token = s.token;
});
onUnauthorized = () => store.getState().logout(true);

const root = document.getElementById("root");
if (!root) throw new Error("#root yok");
createRoot(root).render(
  <StrictMode>
    <StudioProvider store={store} api={api}>
      <App />
    </StudioProvider>
  </StrictMode>,
);
