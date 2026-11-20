/**
 * Thin fetch wrapper: base URL, bearer token, typed errors, and one global
 * hook for 401 so an expired session signs the user out wherever it happens.
 */

import { configureWake, ensureAwake, noteApiResponse, noteApiUnreachable, WakeTimeoutError } from "./wake";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");

export function apiUrl(path: string): string {
  return `${BASE_URL}${path}`;
}

configureWake(apiUrl("/health"));

export class ApiError extends Error {
  /** HTTP status, or 0 when the server could not be reached. */
  readonly status: number;
  /** Seconds from the Retry-After header (429 rate limit, 503 busy). */
  readonly retryAfter?: number;

  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

let currentToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

/** Called by the auth provider; the token never leaves this module otherwise. */
export function configureAuth(token: string | null, unauthorized: (() => void) | null) {
  currentToken = token;
  onUnauthorized = unauthorized;
}

const FALLBACK_MESSAGES: Record<number, string> = {
  0: "Can't reach Policy Copilot. Check your connection and that the service is running.",
  401: "Your session has expired. Sign in again to continue.",
  403: "Your account doesn't have permission to do that.",
  404: "That item doesn't exist or isn't available to you.",
  429: "You've asked too many questions in a short time. Wait a moment and try again.",
  500: "Policy Copilot hit an unexpected error. Try again.",
  503: "The answer service is temporarily unavailable. Try again shortly.",
};

function fallbackMessage(status: number): string {
  return FALLBACK_MESSAGES[status] ?? FALLBACK_MESSAGES[500]!;
}

/** FastAPI errors are {detail: string} or, for validation, {detail: [{msg}]}. */
async function errorFromResponse(response: Response): Promise<ApiError> {
  let message = fallbackMessage(response.status);
  try {
    const body = await response.json();
    if (typeof body?.detail === "string" && response.status !== 500) {
      message = body.detail.trim();
    } else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      message = String(body.detail[0].msg);
    }
  } catch {
    // Non-JSON body (proxy error page): keep the fallback message.
  }
  const retryHeader = Number(response.headers.get("Retry-After"));
  const retryAfter = Number.isFinite(retryHeader) && retryHeader > 0 ? retryHeader : undefined;
  return new ApiError(response.status, message, retryAfter);
}

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  accept?: string;
  /**
   * Sign-in: send no session token, and treat 401 as an ordinary answer
   * (wrong credentials) rather than an expired session.
   */
  anonymous?: boolean;
}

/** Waits for a sleeping API (free-tier cold start); see api/wake.ts. */
async function awake(): Promise<void> {
  try {
    await ensureAwake();
  } catch (error) {
    if (error instanceof WakeTimeoutError) throw new ApiError(0, error.message);
    throw error;
  }
}

/**
 * Gateway errors come from the hosting proxy (the API never sends them):
 * the request didn't reach the application.
 */
const GATEWAY_STATUSES = new Set([502, 504]);

/** Performs the request and returns the raw Response if it was 2xx. */
export async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  const token = options.anonymous ? null : currentToken;
  const headers: Record<string, string> = { Accept: options.accept ?? "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const method = options.method ?? "GET";

  const send = async (): Promise<Response | null> => {
    await awake();
    try {
      const response = await fetch(apiUrl(path), {
        method,
        headers,
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
        signal: options.signal,
        cache: "no-store",
      });
      if (GATEWAY_STATUSES.has(response.status)) {
        noteApiUnreachable();
        return null;
      }
      noteApiResponse();
      return response;
    } catch (error) {
      if (isAbortError(error)) throw error;
      noteApiUnreachable();
      return null;
    }
  };

  // Only reads are retried after the API was unreachable (it may have just
  // gone to sleep). Writes, and above all questions, are never re-sent:
  // the server may have received them.
  let response = await send();
  if (!response && method === "GET") response = await send();
  if (!response) throw new ApiError(0, fallbackMessage(0));

  if (!response.ok) {
    const error = await errorFromResponse(response);
    // A rejected session token means the session is over.
    if (response.status === 401 && !options.anonymous) {
      onUnauthorized?.();
      throw new ApiError(401, fallbackMessage(401));
    }
    throw error;
  }
  return response;
}

export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
