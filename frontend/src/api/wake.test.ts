import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "./client";
import {
  ensureAwake,
  MAX_WAIT_MS,
  noteApiResponse,
  resetWakeForTests,
  STALE_AFTER_MS,
  WakeTimeoutError,
} from "./wake";

/** fetch stub: /health answers per `healthy()`, other calls return 200 JSON. */
function stubApi(healthy: () => boolean) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/health")) {
        if (!healthy()) throw new TypeError("Failed to fetch");
        return new Response('{"status":"ok"}', { status: 200 });
      }
      return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  return calls;
}

beforeEach(() => {
  resetWakeForTests();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ensureAwake", () => {
  it("costs one quick check when the API is already up, then nothing while fresh", async () => {
    const calls = stubApi(() => true);
    await ensureAwake();
    await ensureAwake();
    expect(calls).toEqual(["GET /api/health"]);
  });

  it("checks again once the last response is older than the sleep window", async () => {
    const calls = stubApi(() => true);
    await ensureAwake();
    vi.advanceTimersByTime(STALE_AFTER_MS + 1);
    await ensureAwake();
    expect(calls.length).toBe(2);
  });

  it("retries with backoff until the API answers, sharing one wake-up", async () => {
    let up = false;
    const calls = stubApi(() => up);

    const first = ensureAwake();
    const second = ensureAwake(); // a concurrent request waits for the same wake-up
    // Checks at 0 s and 1 s fail; the API is up for the one at 3 s (1 s, then 2 s backoff).
    await vi.advanceTimersByTimeAsync(2_500);
    up = true;
    await vi.advanceTimersByTimeAsync(1_000);
    await Promise.all([first, second]);

    expect(calls.length).toBe(3);
  });

  it("gives up after the maximum wait", async () => {
    stubApi(() => false);
    const result = ensureAwake().then(() => "woke", (error) => error);
    await vi.advanceTimersByTimeAsync(MAX_WAIT_MS + 10_000);
    expect(await result).toBeInstanceOf(WakeTimeoutError);
  });
});

describe("request during a cold start", () => {
  it("waits for the API, then sends the original request exactly once", async () => {
    let up = false;
    const calls = stubApi(() => up);

    const pending = request("/conversations/c1/messages/stream", { method: "POST", body: { question: "q" } });
    await vi.advanceTimersByTimeAsync(3_000);
    expect(calls.filter((c) => c.startsWith("POST"))).toEqual([]); // nothing sent while asleep
    up = true;
    await vi.advanceTimersByTimeAsync(4_000);
    await pending;

    expect(calls.filter((c) => c.startsWith("POST"))).toEqual(["POST /api/conversations/c1/messages/stream"]);
  });

  it("never re-sends a write that failed in flight", async () => {
    noteApiResponse();
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? "GET"} ${url}`);
        if (url.endsWith("/health")) return new Response("{}", { status: 200 });
        throw new TypeError("connection reset");
      }),
    );

    await expect(request("/auth/login", { method: "POST", body: {}, anonymous: true })).rejects.toMatchObject({ status: 0 });
    expect(calls.filter((c) => c.startsWith("POST"))).toHaveLength(1);
  });

  it("retries a read once after the API turned out to be asleep", async () => {
    noteApiResponse();
    let failures = 1;
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? "GET"} ${url}`);
        if (url.endsWith("/health")) return new Response("{}", { status: 200 });
        if (failures-- > 0) return new Response("<html>Bad gateway</html>", { status: 502 });
        return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
      }),
    );

    await request("/conversations");
    expect(calls).toEqual(["GET /api/conversations", "GET /api/health", "GET /api/conversations"]);
  });
});
