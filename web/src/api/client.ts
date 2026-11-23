import type { CommandRequest, CommandResult, ImportRequest, NodeRef, Snapshot } from "../types";

/** REST surface used by the store; tests replace it with a fake. */
export interface StudioApi {
  listProjects(): Promise<{ id: string; name: string }[]>;
  createProject(meta: ImportRequest, file: File): Promise<Snapshot>;
  snapshot(projectId: string): Promise<Snapshot>;
  command(projectId: string, req: CommandRequest): Promise<CommandResult>;
  lock(projectId: string, ref: NodeRef): Promise<boolean>;
  matrixUrl(projectId: string): string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function detail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    return res.statusText;
  }
}

export function createRestApi(getUser: () => string, fetchFn: typeof fetch = (...a) => fetch(...a)): StudioApi {
  const headers = (extra: Record<string, string> = {}) => ({ "X-User": getUser(), ...extra });

  async function json<T>(res: Response): Promise<T> {
    if (!res.ok) throw new ApiError(await detail(res), res.status);
    return (await res.json()) as T;
  }

  return {
    async listProjects() {
      const raw = await json<unknown[]>(await fetchFn("/projects", { headers: headers() }));
      // Contract: `[{id, name}]`; tolerate `[[id, name]]` (ProjectService.projects tuples).
      return raw.map((p) => (Array.isArray(p) ? { id: String(p[0]), name: String(p[1]) } : (p as { id: string; name: string })));
    },
    async createProject(meta, file) {
      const form = new FormData();
      form.append("meta", JSON.stringify(meta));
      form.append("file", file, file.name);
      return json<Snapshot>(await fetchFn("/projects", { method: "POST", headers: headers(), body: form }));
    },
    async snapshot(projectId) {
      return json<Snapshot>(await fetchFn(`/projects/${encodeURIComponent(projectId)}/snapshot`, { headers: headers() }));
    },
    async command(projectId, req) {
      const res = await fetchFn(`/projects/${encodeURIComponent(projectId)}/commands`, {
        method: "POST",
        headers: headers({ "Content-Type": "application/json" }),
        body: JSON.stringify(req),
      });
      // 409, 422 and 423 carry a CommandResult with `accepted: false`.
      if (res.status === 409 || res.status === 422 || res.status === 423) {
        try {
          const body = (await res.json()) as CommandResult | { detail?: CommandResult };
          const result = "accepted" in body ? body : body.detail;
          if (result && "accepted" in result) return result;
        } catch {
          /* fall through */
        }
        const reason = res.status === 409 ? "version_conflict" : res.status === 423 ? "locked" : "invalid";
        return { accepted: false, seq: 0, reason, current_versions: {} };
      }
      return json<CommandResult>(res);
    },
    async lock(projectId, ref) {
      const res = await fetchFn(`/projects/${encodeURIComponent(projectId)}/locks`, {
        method: "POST",
        headers: headers({ "Content-Type": "application/json" }),
        body: JSON.stringify({ ref }),
      });
      if (res.status === 423) return false;
      if (!res.ok) throw new ApiError(await detail(res), res.status);
      return true;
    },
    matrixUrl(projectId) {
      return `/projects/${encodeURIComponent(projectId)}/matrix.xlsx`;
    },
  };
}
