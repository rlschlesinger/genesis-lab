// One WebSocket subscription to a run's snapshots, with automatic reconnection.
//
// Plain TypeScript, no React: the reconnection rules are the tricky part, and keeping them
// out of components lets tests drive them with a fake WebSocket and a fake clock.
//
// Rules (docs/API.md, "The stream"):
//   - "hello" means connected; the reconnect delay resets.
//   - The connection drops unexpectedly (server restarted, laptop slept): reconnect after
//     0.5 s, then 1, 2, 4, 8 s (capped), forever, showing "reconnecting".
//   - "gone" with replaced_by (the run was reset): follow the new run at once.
//   - "gone" without it, or close code 4404: the run no longer exists; stop.
//   - A message this lab can't understand (ProtocolError, close 4422): stop and say why;
//     retrying would fail the same way.

import { ProtocolError, parseServerMessage } from "../api/parse";
import type { HelloMessage, Snapshot } from "../api/types";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "gone" | "error" | "closed";

export interface StreamHandlers {
  onHello(message: HelloMessage): void;
  onSnapshot(snapshot: Snapshot): void;
  onStatus(status: StreamStatus, detail?: string): void;
  /** The run was reset: the stream now follows ``newRunId``. */
  onRunReplaced(newRunId: string): void;
}

export interface SocketLike {
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number; reason: string }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  close(code?: number, reason?: string): void;
}

export interface StreamOptions {
  fps?: number;
  /** Builds the socket; tests pass a fake. */
  openSocket?: (url: string) => SocketLike;
  /** ws://host or wss://host; defaults to the page's own host (Vite proxies /api in dev). */
  origin?: string;
}

export const CLOSE_UNKNOWN_RUN = 4404;
export const CLOSE_BAD_REQUEST = 4422;
const FIRST_DELAY_MS = 500;
const MAX_DELAY_MS = 8000;

function pageOrigin(): string {
  const { protocol, host } = window.location;
  return `${protocol === "https:" ? "wss" : "ws"}://${host}`;
}

export class StreamConnection {
  private socket: SocketLike | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private delay = FIRST_DELAY_MS;
  private stopped = false;
  private readonly fps: number;
  private readonly openSocket: (url: string) => SocketLike;
  private readonly origin: string | undefined;

  constructor(
    private runId: string,
    private readonly handlers: StreamHandlers,
    options: StreamOptions = {},
  ) {
    this.fps = options.fps ?? 15;
    this.openSocket = options.openSocket ?? ((url) => new WebSocket(url) as unknown as SocketLike);
    this.origin = options.origin;
  }

  get currentRunId(): string {
    return this.runId;
  }

  /** The delay before the next reconnection attempt (exposed for tests and the status line). */
  get nextDelayMs(): number {
    return this.delay;
  }

  start(): void {
    this.stopped = false;
    this.open("connecting");
  }

  /** Close for good (the viewer chose another run, or left the page). */
  close(): void {
    this.stopped = true;
    this.clearRetry();
    this.detach()?.close(1000, "viewer left");
    this.handlers.onStatus("closed");
  }

  private open(status: StreamStatus): void {
    this.handlers.onStatus(status);
    const url = `${this.origin ?? pageOrigin()}/api/runs/${encodeURIComponent(this.runId)}/stream?fps=${this.fps}`;
    const socket = this.openSocket(url);
    this.socket = socket;
    socket.onmessage = (event) => this.receive(socket, event.data);
    socket.onclose = (event) => this.closed(socket, event.code, event.reason);
    socket.onerror = () => {}; // a failed connection also fires close, handled there
  }

  private receive(socket: SocketLike, data: unknown): void {
    if (socket !== this.socket) return; // a message from a socket we've already left
    let message;
    try {
      message = parseServerMessage(String(data));
    } catch (error) {
      this.fail(error instanceof ProtocolError ? error.message : "unreadable message");
      return;
    }
    switch (message.type) {
      case "hello":
        this.delay = FIRST_DELAY_MS;
        this.handlers.onStatus("live");
        this.handlers.onHello(message);
        break;
      case "snapshot":
        this.handlers.onSnapshot(message);
        break;
      case "gone":
        if (message.replaced_by) {
          this.detach()?.close(1000, "following the reset run");
          this.runId = message.replaced_by;
          this.handlers.onRunReplaced(message.replaced_by);
          this.open("connecting");
        } else {
          this.stopped = true;
          this.detach()?.close(1000, "run gone");
          this.handlers.onStatus("gone", "This run no longer exists.");
        }
        break;
    }
  }

  private closed(socket: SocketLike, code: number, reason: string): void {
    if (socket !== this.socket || this.stopped) return;
    this.socket = null;
    if (code === CLOSE_UNKNOWN_RUN) {
      this.stopped = true;
      this.handlers.onStatus("gone", "This run no longer exists.");
      return;
    }
    if (code === CLOSE_BAD_REQUEST) {
      this.fail(reason || "the server refused the stream request");
      return;
    }
    this.handlers.onStatus("reconnecting", `Connection lost. Trying again in ${this.delay / 1000} s.`);
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      if (!this.stopped) this.open("reconnecting");
    }, this.delay);
    this.delay = Math.min(this.delay * 2, MAX_DELAY_MS);
  }

  private fail(detail: string): void {
    this.stopped = true;
    this.clearRetry();
    this.detach()?.close(1000, "protocol error");
    this.handlers.onStatus("error", detail);
  }

  private detach(): SocketLike | null {
    const socket = this.socket;
    this.socket = null;
    return socket;
  }

  private clearRetry(): void {
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }
}
