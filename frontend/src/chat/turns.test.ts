import { afterEach, describe, expect, it, vi } from "vitest";
import { abortAllTurns, getTurn, startTurn, stopTurn, type Turn } from "./turns";

/*
  The turn lifecycle against the event sequences post_message_stream emits
  (app/api/conversations.py). fetch is replaced by a stub that streams the
  given SSE text, so these run without a server.
*/

const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

const SAVED_TURN = [
  sse("status", { stage: "rewriting" }),
  sse("question", { standalone: "How many leave days?" }),
  sse("status", { stage: "generation" }),
  sse("token", { text: "24 days " }),
  sse("token", { text: "[Source 1]." }),
  sse("answer", { text: "24 days [Source 1]." }),
  sse("citations", {
    sources: [{ source: 1, document: "Leave", section: null, chunk_id: "c1", score: 0.8 }],
  }),
  sse("saved", { message_id: "m1" }),
  sse("done", {}),
];

function stubStream(parts: string[], { holdOpen = false, status = 200, headers = {} } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (status !== 200) {
        return new Response(JSON.stringify({ detail: "Rate limit exceeded. Try again later." }), {
          status,
          headers: { "Content-Type": "application/json", ...headers },
        });
      }
      const encoder = new TextEncoder();
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          for (const part of parts) controller.enqueue(encoder.encode(part));
          if (holdOpen) {
            init?.signal?.addEventListener("abort", () =>
              controller.error(new DOMException("Aborted", "AbortError")),
            );
          } else {
            controller.close();
          }
        },
      });
      return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
    }),
  );
}

let conversation = 0;

/** Starts a turn in a fresh conversation; resolves with its state once settled. */
function run(question = "How many leave days?"): Promise<Turn | undefined> {
  const id = `conv-${++conversation}`;
  // onSettled fires after the final state is written.
  return new Promise((resolve) => startTurn(id, question, 0, { onSettled: () => resolve(getTurn(id)) }));
}

afterEach(() => {
  abortAllTurns();
  vi.unstubAllGlobals();
});

describe("turn lifecycle", () => {
  it("ends saved, with the validated answer replacing streamed tokens", async () => {
    stubStream(SAVED_TURN);
    const turn = await run();
    expect(turn?.phase).toBe("saved");
    expect(turn?.draft).toBe("24 days [Source 1].");
    expect(turn?.answer).toBe("24 days [Source 1].");
    expect(turn?.citations).toHaveLength(1);
    expect(turn?.messageId).toBe("m1");
    expect(turn?.standalone).toBe("How many leave days?");
  });

  it("fails with the server's message when the model fails mid-stream", async () => {
    stubStream([
      sse("status", { stage: "rewriting" }),
      sse("status", { stage: "generation" }),
      sse("token", { text: "partial" }),
      sse("error", { detail: "The answer service is temporarily unavailable." }),
      sse("done", {}),
    ]);
    const turn = await run();
    expect(turn?.phase).toBe("failed");
    expect(turn?.error).toBe("The answer service is temporarily unavailable.");
    expect(turn?.messageId).toBeUndefined();
  });

  it("asks the server to confirm when the stream ends without saved or error", async () => {
    stubStream([sse("status", { stage: "generation" }), sse("token", { text: "cut off" })]);
    const turn = await run();
    expect(turn?.phase).toBe("checking");
  });

  it("records the retry time from a 429 before the stream opens", async () => {
    stubStream([], { status: 429, headers: { "Retry-After": "30" } });
    const before = Date.now();
    const turn = await run();
    expect(turn?.phase).toBe("failed");
    expect(turn?.retryAt).toBeGreaterThanOrEqual(before + 30_000);
  });

  it("ends stopped when the user stops it before it is saved", async () => {
    stubStream([sse("status", { stage: "generation" }), sse("token", { text: "Writing" })], { holdOpen: true });
    const id = `conv-${++conversation}`;
    const settled = new Promise<Turn | undefined>((resolve) =>
      startTurn(id, "q", 0, { onSettled: () => resolve(getTurn(id)) }),
    );
    await new Promise((r) => setTimeout(r, 20));
    stopTurn(id);
    expect((await settled)?.phase).toBe("stopped");
  });

  it("ignores a second question while one is in flight in the same conversation", async () => {
    stubStream([sse("status", { stage: "generation" })], { holdOpen: true });
    const id = `conv-${++conversation}`;
    startTurn(id, "first", 0);
    startTurn(id, "second", 0);
    await new Promise((r) => setTimeout(r, 10));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(getTurn(id)?.question).toBe("first");
  });
});
