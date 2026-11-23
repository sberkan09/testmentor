import { useEffect } from "react";
import { useActions, useStudio } from "./context";
import { ProjectsPage, UserGate } from "./components/ProjectsPage";
import { Studio } from "./components/Studio";
import { Toasts } from "./components/ui";

export function App() {
  const user = useStudio((s) => s.user);
  const authMode = useStudio((s) => s.authMode);
  const token = useStudio((s) => s.token);
  const open = useStudio((s) => s.server !== null);
  const { loadAuthConfig } = useActions();

  useEffect(() => {
    if (authMode === null) void loadAuthConfig();
  }, [authMode, loadAuthConfig]);

  // Password mode (paket 10): a token is needed; header mode: a name is enough.
  const signedIn = authMode === "password" ? !!token && !!user : !!user;
  return (
    <>
      {authMode === null ? null : !signedIn ? <UserGate /> : open ? <Studio /> : <ProjectsPage />}
      <Toasts />
    </>
  );
}
