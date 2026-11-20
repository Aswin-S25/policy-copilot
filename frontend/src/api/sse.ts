/**
 * Server-Sent Events over fetch.
 *
 * EventSource can't be used: the stream endpoint is a POST with a JSON body
 * and a bearer header. The wire format is the same (app/api/sse.py):
 *
 *   event: <name>\n
 *   data: <json>\n
 *   \n
 */

/** A blank line ends an event; tolerate CRLF from proxies. Not global: no lastIndex state. */
const BLOCK_END = /\r?\n\r?\n/;

export interface RawEvent {
  event: string;
  data: unknown;
}

function parseBlock(block: string): RawEvent | null {
  let event = "message";
  const data: string[] = [];

  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue; // blank or comment
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }

  if (data.length === 0) return null;
  const text = data.join("\n");
  try {
    return { event, data: JSON.parse(text) };
  } catch {
    return { event, data: text };
  }
}

/** Yields events as they arrive. Ends when the server closes the stream. */
export async function* readEventStream(response: Response): AsyncGenerator<RawEvent> {
  if (!response.body) return;

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;

      // An event ends at a blank line; a chunk may hold several or a fragment.
      let boundary = BLOCK_END.exec(buffer);
      while (boundary) {
        const block = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        const parsed = parseBlock(block);
        if (parsed) yield parsed;
        boundary = BLOCK_END.exec(buffer);
      }
    }
    const tail = parseBlock(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}
