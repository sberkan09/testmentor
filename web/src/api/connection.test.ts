import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeSocket, ev, snapshot } from "../test/fixtures";
import { ProjectConnection } from "./connection";

beforeEach(() => {
  FakeSocket.instances = [];
});

function make(getAfter: () => number, onEvent = vi.fn(), onSnapshot = vi.fn()) {
  const timers: { fn: () => void; ms: number }[] = [];
  const conn = new ProjectConnection({
    url: (after) => `ws://x/projects/P/events?after=${after}`,
    socketFactory: (u) => new FakeSocket(u),
    getAfter,
    onEvent,
    onSnapshot,
    setTimer: (fn, ms) => {
      timers.push({ fn, ms });
      return timers.length;
    },
    clearTimer: () => undefined,
    baseDelayMs: 100,
    maxDelayMs: 1000,
  });
  return { conn, timers, onEvent, onSnapshot };
}

describe("ProjectConnection", () => {
  it("olayları iletir, snapshot mesajını ayrı iletir", () => {
    const { conn, onEvent, onSnapshot } = make(() => 0);
    conn.start();
    const s = FakeSocket.instances[0] as FakeSocket;
    s.open();
    s.push(ev(1, "node_updated", {}));
    s.push({ type: "snapshot", snapshot: snapshot(9) });
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onSnapshot).toHaveBeenCalledWith(expect.objectContaining({ seq: 9 }));
    expect(conn.status).toBe("open");
  });

  it("kopunca üstel geri çekilmeyle, son seq ile yeniden bağlanır", () => {
    let seq = 4;
    const { conn, timers } = make(() => seq);
    conn.start();
    expect(FakeSocket.instances[0]?.url).toContain("after=4");
    (FakeSocket.instances[0] as FakeSocket).drop();
    expect(conn.status).toBe("reconnecting");
    expect(timers[0]?.ms).toBe(100);
    seq = 7; // kopukken de durum ilerleyebilir; yeniden bağlanırken güncel seq okunur
    timers[0]?.fn();
    expect(FakeSocket.instances).toHaveLength(2);
    expect(FakeSocket.instances[1]?.url).toContain("after=7");
    (FakeSocket.instances[1] as FakeSocket).drop(); // açılamadan koptu: bekleme iki katına çıkar
    expect(timers[1]?.ms).toBe(200);
    timers[1]?.fn();
    (FakeSocket.instances[2] as FakeSocket).open();
    (FakeSocket.instances[2] as FakeSocket).drop();
    expect(timers[2]?.ms).toBe(100); // açılış sayacı sıfırlar
  });

  it("stop() sonrası yeniden bağlanmaz", () => {
    const { conn, timers } = make(() => 0);
    conn.start();
    const s = FakeSocket.instances[0] as FakeSocket;
    conn.stop();
    s.drop();
    expect(timers).toHaveLength(0);
    expect(s.closed).toBe(true);
    expect(conn.status).toBe("closed");
  });

  it("resync() eski soketi kapatır ve güncel seq ile yenisini açar", () => {
    const { conn } = make(() => 3);
    conn.start();
    conn.resync();
    expect(FakeSocket.instances).toHaveLength(2);
    expect(FakeSocket.instances[0]?.closed).toBe(true);
  });

  it("ping mesajına pong döner, bozuk mesajı yok sayar", () => {
    const { conn, onEvent } = make(() => 0);
    conn.start();
    const s = FakeSocket.instances[0] as FakeSocket;
    s.push({ type: "ping" });
    s.onmessage?.({ data: "{bozuk" });
    expect(s.sent).toEqual([JSON.stringify({ type: "pong" })]);
    expect(onEvent).not.toHaveBeenCalled();
  });
});
