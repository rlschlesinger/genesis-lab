import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import hello from "../api/__fixtures__/hello.json";
import snapshot from "../api/__fixtures__/snapshot.json";
import {
  CLOSE_BAD_REQUEST,
  CLOSE_UNKNOWN_RUN,
  type SocketLike,
  StreamConnection,
  type StreamHandlers,
  type StreamStatus,
} from "./connection";

/** A socket the test controls: it records what was opened and lets the test deliver
 *  messages or drop the connection. */
class FakeSocket implements SocketLike {
  onopen: SocketLike["onopen"] = null;
  onmessage: SocketLike["onmessage"] = null;
  onclose: SocketLike["onclose"] = null;
  onerror: SocketLike["onerror"] = null;
  closedBy: number | null = null;
  constructor(readonly url: string) {}
  deliver(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  drop(code = 1006, reason = "") {
    this.onclose?.({ code, reason });
  }
  close(code = 1000) {
    this.closedBy = code;
  }
}

function setup(runId = "run-a") {
  const sockets: FakeSocket[] = [];
  const statuses: StreamStatus[] = [];
  const handlers: StreamHandlers = {
    onHello: vi.fn(),
    onSnapshot: vi.fn(),
    onStatus: vi.fn((status: StreamStatus) => statuses.push(status)),
    onRunReplaced: vi.fn(),
  };
  const connection = new StreamConnection(runId, handlers, {
    fps: 10,
    origin: "ws://lab.test",
    openSocket: (url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket;
    },
  });
  connection.start();
  const latest = () => sockets[sockets.length - 1]!;
  return { connection, handlers, sockets, statuses, latest };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("StreamConnection", () => {
  it("opens the documented URL and goes live on hello", () => {
    const { handlers, latest, statuses } = setup();
    expect(latest().url).toBe("ws://lab.test/api/runs/run-a/stream?fps=10");
    latest().deliver(hello);
    latest().deliver(snapshot);
    expect(statuses).toEqual(["connecting", "live"]);
    expect(handlers.onHello).toHaveBeenCalledOnce();
    expect(handlers.onSnapshot).toHaveBeenCalledWith(snapshot);
  });

  it("reconnects after a drop, waiting 0.5, 1, 2, 4, 8, 8 s", () => {
    const { connection, sockets, latest } = setup();
    const waits: number[] = [];
    for (let i = 0; i < 6; i++) {
      waits.push(connection.nextDelayMs);
      latest().drop();
      vi.advanceTimersByTime(waits[i]! - 1);
      expect(sockets).toHaveLength(i + 1); // not yet
      vi.advanceTimersByTime(1);
      expect(sockets).toHaveLength(i + 2); // reopened exactly on time
    }
    expect(waits).toEqual([500, 1000, 2000, 4000, 8000, 8000]);
  });

  it("starts the backoff over once a reconnection succeeds", () => {
    const { connection, latest } = setup();
    latest().drop();
    vi.advanceTimersByTime(500);
    latest().drop();
    vi.advanceTimersByTime(1000);
    expect(connection.nextDelayMs).toBe(2000); // two drops: 0.5 s, then 1 s, next 2 s
    latest().deliver(hello);
    expect(connection.nextDelayMs).toBe(500);
  });

  it("follows a reset run to its new ID at once", () => {
    const { connection, handlers, sockets, latest } = setup();
    latest().deliver({ type: "gone", run_id: "run-a", replaced_by: "run-b" });
    expect(handlers.onRunReplaced).toHaveBeenCalledWith("run-b");
    expect(connection.currentRunId).toBe("run-b");
    expect(sockets).toHaveLength(2);
    expect(latest().url).toContain("/api/runs/run-b/stream");
  });

  it.each([
    ["a gone message without a replacement", (s: FakeSocket) => s.deliver({ type: "gone", run_id: "run-a", replaced_by: null }), "gone"],
    ["close code 4404", (s: FakeSocket) => s.drop(CLOSE_UNKNOWN_RUN), "gone"],
    ["close code 4422", (s: FakeSocket) => s.drop(CLOSE_BAD_REQUEST, "fps must be 1-30"), "error"],
    ["a message from another protocol version", (s: FakeSocket) => s.deliver({ ...snapshot, version: 9 }), "error"],
  ] as const)("stops for good on %s", (_case, act, final) => {
    const { sockets, statuses, latest } = setup();
    act(latest());
    expect(statuses[statuses.length - 1]).toBe(final);
    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(1); // no retry
  });

  it("close() stops a pending reconnection", () => {
    const { connection, sockets, statuses, latest } = setup();
    latest().drop();
    connection.close();
    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(1);
    expect(statuses[statuses.length - 1]).toBe("closed");
  });

  it("ignores messages and drops from a socket it has already left", () => {
    const { handlers, sockets, latest } = setup();
    const old = latest();
    latest().deliver({ type: "gone", run_id: "run-a", replaced_by: "run-b" });
    old.deliver(snapshot);
    old.drop();
    expect(handlers.onSnapshot).not.toHaveBeenCalled();
    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(2); // the old socket's drop caused no reconnection
  });
});
