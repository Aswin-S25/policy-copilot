/**
 * Cold-start handling for a free-tier API that sleeps when idle.
 *
 * Before a request goes to an API that hasn't answered recently, the app
 * checks GET /health. If that doesn't answer quickly, the API is waking up:
 * the UI says so, and the check is retried with exponential backoff up to a
 * maximum total wait. Once it answers, the original request continues.
 *
 * - No background polling: a check runs only when the app needs the API.
 * - Concurrent requests share one wake-up check.
 * - The original request is sent once, after the API is awake, so a question
 *   (which starts an LLM generation) is never sent twice by this mechanism.
 */
import { useSyncExternalStore } from "react";

export type WakeState = "awake" | "waking" | "unreachable";

/** Treat the API as possibly asleep after this long without a response. */
export const STALE_AFTER_MS = 10 * 60_000;
/** First check is short so an awake API costs little; later ones allow a slow boot. */
export const FIRST_PROBE_TIMEOUT_MS = 3_000;
export const PROBE_TIMEOUT_MS = 10_000;
export const INITIAL_BACKOFF_MS = 1_000;
export const MAX_BACKOFF_MS = 8_000;
/** Give up after this long; the user can try again. */
export const MAX_WAIT_MS = 120_000;

let healthUrl = "/api/health";
let lastResponseAt = 0;
let state: WakeState = "awake";
let pending: Promise<void> | null = null;
const listeners = new Set<() => void>();

function setState(next: WakeState) {
  if (state === next) return;
  state = next;
  for (const listener of listeners) listener();
}

export function configureWake(url: string) {
  healthUrl = url;
}

/** Any HTTP response (even an error status) proves the API is up. */
export function noteApiResponse() {
  lastResponseAt = Date.now();
  setState("awake");
}

/** A request failed without reaching the API: check again before the next one. */
export function noteApiUnreachable() {
  lastResponseAt = 0;
}

export class WakeTimeoutError extends Error {
  constructor() {
    super("Policy Copilot didn't wake up in time. Check your connection and try again.");
    this.name = "WakeTimeoutError";
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function probe(timeoutMs: number): Promise<boolean> {
  try {
    const response = await fetch(healthUrl, { cache: "no-store", signal: AbortSignal.timeout(timeoutMs) });
    return response.ok;
  } catch {
    return false; // timeout, network error, or the host's "starting" error page
  }
}

async function wake(): Promise<void> {
  const started = Date.now();
  let backoff = INITIAL_BACKOFF_MS;
  for (let attempt = 0; ; attempt++) {
    if (await probe(attempt === 0 ? FIRST_PROBE_TIMEOUT_MS : PROBE_TIMEOUT_MS)) {
      noteApiResponse();
      return;
    }
    setState("waking");
    if (Date.now() - started + backoff > MAX_WAIT_MS) {
      setState("unreachable");
      throw new WakeTimeoutError();
    }
    await sleep(backoff);
    backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
  }
}

/** Resolves once the API answers; throws WakeTimeoutError after MAX_WAIT_MS. */
export function ensureAwake(): Promise<void> {
  if (Date.now() - lastResponseAt < STALE_AFTER_MS) return Promise.resolve();
  pending ??= wake().finally(() => {
    pending = null;
  });
  return pending;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useWakeState(): WakeState {
  return useSyncExternalStore(subscribe, () => state);
}

/** Tests only. */
export function resetWakeForTests() {
  lastResponseAt = 0;
  state = "awake";
  pending = null;
  listeners.clear();
}
