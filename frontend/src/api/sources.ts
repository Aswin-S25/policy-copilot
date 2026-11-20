import { requestJson } from "./client";
import type { SourcePassage } from "./types";

// Passages don't change between ingestions, so a fetched passage is reused
// for the rest of the session instead of being requested on every click.
const cache = new Map<string, SourcePassage>();
const inFlight = new Map<string, Promise<SourcePassage>>();

export function cachedPassage(chunkId: string): SourcePassage | undefined {
  return cache.get(chunkId);
}

export function getPassage(chunkId: string): Promise<SourcePassage> {
  const hit = cache.get(chunkId);
  if (hit) return Promise.resolve(hit);

  let pending = inFlight.get(chunkId);
  if (!pending) {
    pending = requestJson<SourcePassage>(`/chunks/${encodeURIComponent(chunkId)}`)
      .then((passage) => {
        cache.set(chunkId, passage);
        return passage;
      })
      .finally(() => inFlight.delete(chunkId));
    inFlight.set(chunkId, pending);
  }
  return pending;
}

/** Sign-out: passages are permission-checked; never show them to the next user. */
export function clearPassageCache() {
  cache.clear();
  inFlight.clear();
}
