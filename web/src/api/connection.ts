import type { ServerEvent, Snapshot } from "../types";

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "closed";

export interface SocketLike {
  onopen: ((ev?: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev?: unknown) => void) | null;
  onerror: ((ev?: unknown) => void) | null;
  send(data: string): void;
  close(): void;
}

export interface ConnectionOptions {
  /** Builds the WebSocket URL for the given last-seen sequence number. */
  url: (after: number) => string;
  socketFactory: (url: string) => SocketLike;
  /** Last sequence number the client has applied; read again at every (re)connect. */
  getAfter: () => number;
  onEvent: (ev: ServerEvent) => void;
  onSnapshot: (snap: Snapshot) => void;
  onStatus?: (status: ConnectionStatus) => void;
  /** The server closed with 4401 (password mode, token missing or expired): no reconnect. */
  onUnauthorized?: () => void;
  baseDelayMs?: number;
  maxDelayMs?: number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (id: unknown) => void;
}

/** WebSocket with `after=<seq>` resume and exponential backoff. A `snapshot` message replaces
 *  the state; every other message is a `ServerEvent`. */
export class ProjectConnection {
  private socket: SocketLike | null = null;
  private attempts = 0;
  private timer: unknown = null;
  private stopped = true;
  status: ConnectionStatus = "closed";

  constructor(private readonly opts: ConnectionOptions) {}

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.open();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer !== null) (this.opts.clearTimer ?? clearTimeout)(this.timer as number);
    this.timer = null;
    const s = this.socket;
    this.socket = null;
    if (s) {
      s.onclose = null;
      s.close();
    }
    this.setStatus("closed");
  }

  /** Drop the current socket and reconnect at once (state is suspected to be out of sync). */
  resync(): void {
    if (this.stopped) return;
    const s = this.socket;
    this.socket = null;
    if (s) {
      s.onclose = null;
      s.close();
    }
    this.open();
  }

  private setStatus(s: ConnectionStatus): void {
    this.status = s;
    this.opts.onStatus?.(s);
  }

  private open(): void {
    this.setStatus(this.attempts === 0 ? "connecting" : "reconnecting");
    const socket = this.opts.socketFactory(this.opts.url(this.opts.getAfter()));
    this.socket = socket;
    socket.onopen = () => {
      this.attempts = 0;
      this.setStatus("open");
    };
    socket.onmessage = (m) => this.handle(m.data);
    socket.onerror = () => undefined;
    socket.onclose = (ev?: unknown) => {
      if (this.socket !== socket) return;
      this.socket = null;
      if ((ev as { code?: number } | undefined)?.code === 4401) {
        this.stop();
        this.opts.onUnauthorized?.();
        return;
      }
      this.scheduleReconnect();
    };
  }

  private handle(data: unknown): void {
    if (typeof data !== "string") return;
    let msg: { type?: string; snapshot?: Snapshot };
    try {
      msg = JSON.parse(data) as typeof msg;
    } catch {
      return;
    }
    if (msg.type === "snapshot" && msg.snapshot) this.opts.onSnapshot(msg.snapshot);
    else if (msg.type === "ping") this.socket?.send(JSON.stringify({ type: "pong" }));
    else if (msg.type === "pong") return;
    else this.opts.onEvent(msg as unknown as ServerEvent);
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    const base = this.opts.baseDelayMs ?? 500;
    const max = this.opts.maxDelayMs ?? 15000;
    const delay = Math.min(max, base * 2 ** this.attempts);
    this.attempts += 1;
    this.setStatus("reconnecting");
    this.timer = (this.opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms)))(() => {
      this.timer = null;
      if (!this.stopped) this.open();
    }, delay);
  }
}

export function browserSocketUrl(projectId: string, after: number, user: string, token: string | null = null): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const q = new URLSearchParams({ after: String(after), user });
  if (token) q.set("token", token);
  return `${proto}://${location.host}/projects/${encodeURIComponent(projectId)}/events?${q.toString()}`;
}
