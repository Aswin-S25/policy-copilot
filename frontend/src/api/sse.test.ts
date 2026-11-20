import { describe, expect, it } from "vitest";
import { readEventStream, type RawEvent } from "./sse";

/** A Response whose body arrives in the given chunks, like a real network stream. */
function streamed(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

async function collect(response: Response): Promise<RawEvent[]> {
  const events: RawEvent[] = [];
  for await (const event of readEventStream(response)) events.push(event);
  return events;
}

describe("readEventStream", () => {
  it("parses the backend's wire format (app/api/sse.py)", async () => {
    const events = await collect(
      streamed([
        'event: status\ndata: {"stage": "rewriting"}\n\n',
        'event: token\ndata: {"text": "Hello"}\n\nevent: done\ndata: {}\n\n',
      ]),
    );
    expect(events).toEqual([
      { event: "status", data: { stage: "rewriting" } },
      { event: "token", data: { text: "Hello" } },
      { event: "done", data: {} },
    ]);
  });

  it("joins an event split across network chunks, even mid-character", async () => {
    // "é" is two UTF-8 bytes; split the stream between them.
    const whole = new TextEncoder().encode('event: token\ndata: {"text": "café"}\n\n');
    const cut = whole.length - 5;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(whole.slice(0, cut));
        controller.enqueue(whole.slice(cut));
        controller.close();
      },
    });
    const events = await collect(new Response(body));
    expect(events).toEqual([{ event: "token", data: { text: "café" } }]);
  });

  it("accepts CRLF line endings, comments and multi-line data", async () => {
    const events = await collect(
      streamed([": keep-alive\r\n\r\nevent: answer\r\ndata: {\"text\":\r\ndata: \"ok\"}\r\n\r\n"]),
    );
    expect(events).toEqual([{ event: "answer", data: { text: "ok" } }]);
  });

  it("keeps non-JSON data as text and flushes a final event without a blank line", async () => {
    const events = await collect(streamed(["event: note\ndata: plain text"]));
    expect(events).toEqual([{ event: "note", data: "plain text" }]);
  });
});
