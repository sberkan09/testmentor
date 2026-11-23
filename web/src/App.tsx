import { useStudio } from "./context";
import { ProjectsPage, UserGate } from "./components/ProjectsPage";
import { Studio } from "./components/Studio";
import { Toasts } from "./components/ui";

export function App() {
  const user = useStudio((s) => s.user);
  const open = useStudio((s) => s.server !== null);
  return (
    <>
      {!user ? <UserGate /> : open ? <Studio /> : <ProjectsPage />}
      <Toasts />
    </>
  );
}
