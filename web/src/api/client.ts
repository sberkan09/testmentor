import type { AuthConfig, CommandRequest, CommandResult, ImportRequest, KbDocumentView, KbRemoveResult, KbUploadResult, LoginResult, NodeRef, Snapshot } from "../types";

/** REST surface used by the store; tests replace it with a fake. */
export interface StudioApi {
  /** Login mode of the server (paket 10); `header` when the server does not say. */
  authConfig(): Promise<AuthConfig>;
  /** Password login; rejects with `ApiError` (401) on a wrong name or password. */
  login(user: string, password: string): Promise<LoginResult>;
  listProjects(): Promise<{ id: string; name: string }[]>;
  createProject(meta: ImportRequest, file: File): Promise<Snapshot>;
  snapshot(projectId: string): Promise<Snapshot>;
  command(projectId: string, req: CommandRequest): Promise<CommandResult>;
  lock(projectId: string, ref: NodeRef): Promise<boolean>;
  matrixUrl(projectId: string): string;
  /** Knowledge base documents of a project (paket 10). */
  listDocuments(projectId: string): Promise<KbDocumentView[]>;
  uploadDocument(projectId: string, file: File): Promise<KbUploadResult>;
  removeDocument(projectId: string, documentId: string): Promise<KbRemoveResult>;
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

export interface AuthHooks {
  /** Token of password login; requests carry it instead of `X-User`. */
  getToken?: () => string | null;
  /** Called on a 401 answer (token missing, expired or forged). */
  onUnauthorized?: () => void;
}

export function createRestApi(getUser: () => string, fetchFn: typeof fetch = (...a) => fetch(...a), hooks: AuthHooks = {}): StudioApi {
  const token = () => hooks.getToken?.() ?? null;
  // HTTP headers carry Latin-1 only; the server decodes the percent-encoded UTF-8 name ("Ayşe").
  const headers = (extra: Record<string, string> = {}): Record<string, string> => {
    const t = token();
    return t ? { Authorization: `Bearer ${t}`, ...extra } : { "X-User": encodeURIComponent(getUser()), ...extra };
  };

  async function json<T>(res: Response): Promise<T> {
    if (!res.ok) {
      if (res.status === 401) hooks.onUnauthorized?.();
      throw new ApiError(await detail(res), res.status);
    }
    return (await res.json()) as T;
  }

  return {
    async authConfig() {
      try {
        const res = await fetchFn("/auth/config");
        if (!res.ok) return { mode: "header" };
        const body = (await res.json()) as Partial<AuthConfig>;
        return { mode: body.mode === "password" ? "password" : "header" };
      } catch {
        return { mode: "header" };
      }
    },
    async login(user, password) {
      const res = await fetchFn("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user, password }),
      });
      if (!res.ok) throw new ApiError(await detail(res), res.status);
      return (await res.json()) as LoginResult;
    },
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
      if (res.status === 401) {
        hooks.onUnauthorized?.();
        throw new ApiError("login required", 401);
      }
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
      if (res.status === 401) hooks.onUnauthorized?.();
      if (!res.ok) throw new ApiError(await detail(res), res.status);
      return true;
    },
    matrixUrl(projectId) {
      // A plain link cannot send a header: password mode passes the token in the query.
      const t = token();
      return `/projects/${encodeURIComponent(projectId)}/matrix.xlsx${t ? `?token=${encodeURIComponent(t)}` : ""}`;
    },
    async listDocuments(projectId) {
      return json<KbDocumentView[]>(await fetchFn(`/projects/${encodeURIComponent(projectId)}/kb/documents`, { headers: headers() }));
    },
    async uploadDocument(projectId, file) {
      const form = new FormData();
      form.append("file", file, file.name);
      return json<KbUploadResult>(
        await fetchFn(`/projects/${encodeURIComponent(projectId)}/kb/documents`, { method: "POST", headers: headers(), body: form }),
      );
    },
    async removeDocument(projectId, documentId) {
      return json<KbRemoveResult>(
        await fetchFn(`/projects/${encodeURIComponent(projectId)}/kb/documents/${encodeURIComponent(documentId)}`, {
          method: "DELETE",
          headers: headers(),
        }),
      );
    },
  };
}
